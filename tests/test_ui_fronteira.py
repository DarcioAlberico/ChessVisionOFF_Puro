"""A fronteira entre a camada pura e o toolkit, cobrada de uma vez para o pacote inteiro (S-549).

**O que já existia, e por que não bastava.** A regra é de 2026-08-31: `src/chess_diagram_ocr/ui/`
é a camada pura -- decisão, medida e tabela --, `qt/` é o toolkit, e o corte do Tk (S-506) deixou
`ui/` sem um só `import` de widget. O que a cobrava eram três guardas de forma diferente e nenhuma
genérica: `test_ui_comandos.test_o_catalogo_nao_importa_tkinter` e
`test_ui_texto_cor.test_o_modulo_de_cor_nao_importa_tkinter` olham **um módulo cada**, e
`test_editor_model.SemTkinterTests` percorre `ui/` inteira -- mas pergunta só por `tkinter` e `PIL`,
que é o toolkit que **saiu**. Um `from PyQt6.QtCore import Qt` num módulo de `ui/` passava pelas
três em verde, e é o import mais provável de todos hoje, porque o Qt é o único toolkit que resta.

**Por `ast`, e não por texto.** Os módulos deste projeto se descrevem uns aos outros em prosa, e
uma dúzia deles cita `import tkinter` ou `PyQt6` no docstring para dizer que aquilo **não** existe
ali. Um `assertNotIn` sobre o texto reprovaria a explicação. Aqui conta só o que o código importa --
inclusive o import tardio dentro de função, o `if TYPE_CHECKING:` e a forma relativa
(`from ..qt import tema`), que são os três jeitos de o toolkit entrar sem aparecer na primeira tela
do arquivo.

**A guarda prova que acha.** É a lição da S-506, em que ~20 varreduras ficaram verdes no corte
por passarem sobre lista vazia, e a da S-505, em que a primeira guarda dos inertes era vácua: um
detector ancorado no arquivo real se apaga junto com o defeito. Então `DetectorTests` afirma a
leitura contra módulos **sintéticos**, e `FronteiraTests` aponta a mesma função para `qt/` -- onde
ela tem de achar o toolkit em quase todo arquivo -- antes de afirmar que em `ui/` não acha nada.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr"
UI = RAIZ / "ui"
QT = RAIZ / "qt"

TOOLKITS: tuple[str, ...] = ("PyQt6", "PySide6", "tkinter", "ttkbootstrap", "chess_diagram_ocr.qt")
"""O que a camada pura não pode importar: os dois Qt, os dois Tk, e o próprio pacote de desenho.

`chess_diagram_ocr.qt` está aqui porque é o caminho indireto: um módulo de `ui/` que importe
`qt/tema.py` não escreve `PyQt6` em linha nenhuma e mesmo assim só abre com o toolkit instalado.
"""

PODEM_IMPORTAR_TOOLKIT: dict[str, str] = {
    "qt": "é o toolkit: o pacote inteiro existe para desenhar e fiar o que `ui/` decide",
    "cli/texto_transcrever.py": (
        "a janela que transcreve as 123 faixas de referência da S-183. Ferramenta de "
        "desenvolvimento com entrada própria, em Tk por decisão do corte (S-506): não abre pelo "
        "`.exe`, e por isso o `tkinter` não entra no `excludes` do `cvoff.spec`"
    ),
}
"""Caminho relativo a `src/chess_diagram_ocr/` -> motivo. Uma pasta isenta o que está dentro dela.

**É um mapa, e não uma lista de perdão**, na forma do `SEM_CHAMADOR` de `test_ui_orfaos.py`:
`test_toda_isencao_ainda_importa_toolkit` exige que quem está aqui **continue** importando
toolkit, senão a isenção envelhece apontando para um arquivo que já não precisa dela.
"""


def _e_toolkit(modulo: str) -> bool:
    return any(modulo == toolkit or modulo.startswith(toolkit + ".") for toolkit in TOOLKITS)


def _pacote_de(caminho: Path, raiz_do_codigo: Path) -> str:
    """O pacote em que `caminho` mora, com pontos: `src/chess_diagram_ocr/ui/x.py` -> `chess_diagram_ocr.ui`.

    É o que resolve o import relativo: `from ..qt import tema` dentro de `chess_diagram_ocr.ui`
    é `chess_diagram_ocr.qt`, e sem esta conta a forma relativa passaria por baixo da guarda.
    """
    partes = caminho.relative_to(raiz_do_codigo).with_suffix("").parts
    if partes and partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join([raiz_do_codigo.name, *partes[:-1]])


def importacoes(arvore: ast.AST, pacote: str) -> list[tuple[int, str]]:
    """Todo módulo que aquela árvore importa, com a linha, já em forma absoluta.

    Conta `import x`, `from x import y`, o relativo (`from ..x import y`, resolvido contra
    `pacote`) e o import por nome -- `importlib.import_module("x")` e `__import__("x")` com literal.
    Não distingue topo de função nem `TYPE_CHECKING`: para a fronteira, um import é um import.
    """
    achados: list[tuple[int, str]] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados.extend((no.lineno, alias.name) for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            if no.level == 0:
                base = no.module or ""
            else:
                acima = pacote.split(".") if pacote else []
                acima = acima[: len(acima) - (no.level - 1)] if no.level > 1 else acima
                base = ".".join(parte for parte in [*acima, no.module or ""] if parte)
            achados.append((no.lineno, base))
            if not _e_toolkit(base):
                # `from chess_diagram_ocr import qt`: a base é inocente e o nome é o toolkit. Quando a
                # base já é toolkit, os nomes são atributos dela e repetir cada um só engrossaria a lista.
                achados.extend((no.lineno, f"{base}.{alias.name}" if base else alias.name) for alias in no.names)
        elif isinstance(no, ast.Call):
            nome = no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
            if nome in ("import_module", "__import__") and no.args:
                primeiro = no.args[0]
                if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
                    achados.append((no.lineno, primeiro.value))
    return achados


def toolkits_importados(caminho: Path, raiz_do_codigo: Path) -> list[str]:
    """`"linha: modulo"` para cada import de toolkit daquele arquivo, na ordem do arquivo."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    pacote = _pacote_de(caminho, raiz_do_codigo)
    # `ast.walk` anda em largura, e não na ordem do arquivo: o `set` tira a repetição e o `sorted`
    # devolve a ordem que quem lê a mensagem espera -- a das linhas.
    achados = {(linha, modulo) for linha, modulo in importacoes(arvore, pacote) if _e_toolkit(modulo)}
    return [f"{linha}: {modulo}" for linha, modulo in sorted(achados)]


def _isento(relativo: str, isencoes: dict[str, str]) -> bool:
    return any(relativo == isencao or relativo.startswith(isencao + "/") for isencao in isencoes)


def violacoes(pasta: Path, raiz_do_codigo: Path, isencoes: dict[str, str] | None = None) -> dict[str, list[str]]:
    """`caminho relativo a raiz_do_codigo -> imports de toolkit`, só para quem tem algum e não está isento.

    `raiz_do_codigo` é a pasta do pacote (`src/chess_diagram_ocr`): é contra ela que o caminho
    relativo e o pacote do import relativo são calculados, e é o que permite apontar a mesma
    função para `ui/`, para `qt/` ou para o pacote inteiro.
    """
    isencoes = isencoes or {}
    achados: dict[str, list[str]] = {}
    for caminho in sorted(pasta.rglob("*.py")):
        relativo = caminho.relative_to(raiz_do_codigo).as_posix()
        if _isento(relativo, isencoes):
            continue
        importados = toolkits_importados(caminho, raiz_do_codigo)
        if importados:
            achados[relativo] = importados
    return achados


class DetectorTests(unittest.TestCase):
    """O leitor, afirmado contra módulos de mentira -- para continuar valendo enquanto `ui/` estiver limpa.

    Um detector que só olha um arquivo limpo não prova que sabe olhar (S-505). Cada caso abaixo é
    um jeito real de o toolkit entrar, e o último é o jeito real de ele **não** ter entrado.
    """

    def _pacote_falso(self, arquivos: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "chess_diagram_ocr"
        for relativo, texto in arquivos.items():
            destino = raiz / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8")
        return raiz

    def test_o_import_de_topo_e_acusado_com_a_linha(self) -> None:
        raiz = self._pacote_falso({"ui/x.py": "import numpy\nimport PyQt6\n"})
        self.assertEqual({"ui/x.py": ["2: PyQt6"]}, violacoes(raiz / "ui", raiz))

    def test_os_cinco_toolkits_sao_acusados_em_qualquer_forma(self) -> None:
        """`import`, `from ... import`, submódulo, apelido e por nome: as formas que aparecem em `qt/`."""
        fonte = (
            "from PyQt6.QtWidgets import QWidget\n"
            "from PySide6 import QtCore\n"
            "import tkinter as tk\n"
            "import ttkbootstrap\n"
            "from chess_diagram_ocr.qt import tema\n"
            "import importlib\n"
            'modulo = importlib.import_module("PyQt6.QtGui")\n'
            "from chess_diagram_ocr import qt as desenho\n"
        )
        raiz = self._pacote_falso({"ui/x.py": fonte})
        self.assertEqual(
            [
                "1: PyQt6.QtWidgets",
                "2: PySide6",
                "3: tkinter",
                "4: ttkbootstrap",
                "5: chess_diagram_ocr.qt",
                "7: PyQt6.QtGui",
                "8: chess_diagram_ocr.qt",
            ],
            violacoes(raiz / "ui", raiz)["ui/x.py"],
        )

    def test_o_import_tardio_e_o_de_tipo_contam(self) -> None:
        """São os dois jeitos de o toolkit entrar sem aparecer na primeira tela do arquivo.

        O import dentro de função é o que `cli/texto_transcrever.py` faz de propósito; o de
        `TYPE_CHECKING` não roda, mas amarra o módulo puro ao toolkit para quem o lê e para o mypy.
        Para a fronteira, um import é um import.
        """
        fonte = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from PyQt6.QtWidgets import QWidget\n"
            "def abrir():\n"
            "    import tkinter as tk\n"
            "    return tk\n"
        )
        raiz = self._pacote_falso({"ui/x.py": fonte})
        self.assertEqual(["3: PyQt6.QtWidgets", "5: tkinter"], violacoes(raiz / "ui", raiz)["ui/x.py"])

    def test_o_import_relativo_do_pacote_de_desenho_e_resolvido(self) -> None:
        """`from ..qt import tema` não escreve `PyQt6` em linha nenhuma, e é toolkit do mesmo jeito."""
        raiz = self._pacote_falso({"ui/x.py": "from ..qt import tema\nfrom ..qt.tema import cor_atual\n", "ui/__init__.py": ""})
        self.assertEqual(["1: chess_diagram_ocr.qt", "2: chess_diagram_ocr.qt.tema"], violacoes(raiz / "ui", raiz)["ui/x.py"])

    def test_o_relativo_de_um_nivel_dentro_de_ui_nao_e_toolkit(self) -> None:
        """`from .tokens import cor` é `chess_diagram_ocr.ui.tokens`, e a resolução não pode confundi-lo."""
        raiz = self._pacote_falso({"ui/x.py": "from .tokens import cor\nfrom . import strings\n"})
        self.assertEqual({}, violacoes(raiz / "ui", raiz))

    def test_citar_o_toolkit_na_prosa_nao_e_importa_lo(self) -> None:
        """O caso mais comum deste projeto: o docstring diz *"não importa `PyQt6`"* -- e não importa."""
        fonte = (
            '"""Puro de propósito: nada aqui faz `import PyQt6`, `from tkinter import ttk` ou `import ttkbootstrap`."""\n'
            "import numpy\n"
            "from chess_diagram_ocr.ui import tokens\n"
            'NOME = "PyQt6"\n'
        )
        raiz = self._pacote_falso({"ui/x.py": fonte})
        self.assertEqual({}, violacoes(raiz / "ui", raiz))

    def test_a_isencao_cobre_o_arquivo_e_a_pasta_e_nada_mais(self) -> None:
        raiz = self._pacote_falso(
            {
                "qt/a.py": "import PyQt6\n",
                "qt/fundo/b.py": "import PyQt6\n",
                "cli/t.py": "import tkinter\n",
                "cli/outro.py": "import tkinter\n",
                "ui/x.py": "import PyQt6\n",
            }
        )
        achados = violacoes(raiz, raiz, {"qt": "toolkit", "cli/t.py": "desenvolvimento"})
        self.assertEqual(["cli/outro.py", "ui/x.py"], sorted(achados))

    def test_um_nome_parecido_nao_e_toolkit(self) -> None:
        """`tkinter_util` ou `PyQt6Compat` seriam falso positivo por prefixo; o corte é no ponto."""
        raiz = self._pacote_falso({"ui/x.py": "import tkinter_util\nimport PyQt6Compat\nfrom chess_diagram_ocr.qtx import y\n"})
        self.assertEqual({}, violacoes(raiz / "ui", raiz))


class FronteiraTests(unittest.TestCase):
    """A pergunta, feita sobre a árvore de verdade."""

    def test_a_varredura_le_a_camada_pura_inteira(self) -> None:
        """Sem isto, um `glob` que deixasse de casar faria o teste de baixo passar sobre nada."""
        modulos = [caminho for caminho in UI.glob("*.py") if caminho.name != "__init__.py"]
        self.assertGreater(len(modulos), 45, "a camada pura tinha 52 módulos em 2026-09-04; a varredura achou menos")
        lidos = sum(len(importacoes(ast.parse(c.read_text(encoding="utf-8")), "chess_diagram_ocr.ui")) for c in modulos)
        self.assertGreater(lidos, len(modulos), "o leitor de imports deixou de achar os imports")

    def test_a_mesma_varredura_acha_o_toolkit_onde_ele_mora(self) -> None:
        """O controle sobre a árvore real: apontada para `qt/`, a função tem de achar o Qt.

        Só `qt/__init__.py` fica de fora da conta: ele declara o `__all__` e mais nada. O resto
        é desenho, e desenho importa `PyQt6`.

        **`qt/preferencias.py` saiu da isenção na S-536.** Ele era o único módulo de `qt/` sem
        toolkit -- montava serviço e motor a partir do arquivo de preferências (S-523) --, e ganhou
        o formulário que edita as opções do motor e o `MotorVivo` que as aplica numa `Tarefa`. As
        duas coisas são widget e thread de Qt; a decisão delas continua em `ui/motor_declarado.py`.
        """
        achados = violacoes(QT, RAIZ)
        com_toolkit = {relativo for relativo in achados if relativo.startswith("qt/")}
        modulos_do_qt = {c.relative_to(RAIZ).as_posix() for c in QT.glob("*.py")}
        sem_widget = {"qt/__init__.py"}
        self.assertEqual(modulos_do_qt - sem_widget, com_toolkit)
        self.assertGreater(len(com_toolkit), 25)

    def test_nenhum_modulo_de_ui_importa_toolkit(self) -> None:
        """**O critério de aceite.** Falha nomeando módulo, linha e o que ele importou.

        `ui/` é a camada que os dois frontends compartilhavam e que sobrou quando um saiu (S-506).
        Um toolkit voltando a entrar aqui é o que faria a decisão deixar de ser afirmável sem
        janela -- que é o que faz cada teste de `ui/` caber num `assertEqual`.
        """
        achados = violacoes(UI, RAIZ)
        self.assertEqual(
            {},
            achados,
            "módulo da camada pura importando toolkit. Decisão fica em `ui/`; desenho e fiação vão para `qt/`:\n"
            + "\n".join(f"  {modulo}: {', '.join(linhas)}" for modulo, linhas in sorted(achados.items())),
        )

    def test_nada_fora_do_pacote_de_desenho_importa_toolkit(self) -> None:
        """A fronteira maior: `service.py`, `detection/`, `text/`, `cli/` -- tudo que não é `qt/`.

        É a promessa da S-31 (a interface é apresentação) e a que a S-500 testou com um segundo
        frontend. A única exceção é declarada com motivo em `PODEM_IMPORTAR_TOOLKIT`.
        """
        achados = violacoes(RAIZ, RAIZ, PODEM_IMPORTAR_TOOLKIT)
        self.assertEqual(
            {},
            achados,
            "toolkit importado fora de `qt/` e sem isenção declarada:\n"
            + "\n".join(f"  {modulo}: {', '.join(linhas)}" for modulo, linhas in sorted(achados.items())),
        )

    def test_toda_isencao_ainda_importa_toolkit(self) -> None:
        """O outro lado do mapa: uma isenção sobre arquivo que já não importa toolkit é isenção vencida.

        E toda isenção tem motivo escrito -- é o que separa um mapa de uma lista de perdão.
        """
        problemas: list[str] = []
        for relativo, motivo in PODEM_IMPORTAR_TOOLKIT.items():
            if not motivo.strip():
                problemas.append(f"{relativo}: isento sem motivo escrito")
            alvo = RAIZ / relativo
            if not alvo.exists():
                problemas.append(f"{relativo}: isento e não existe")
                continue
            achados = violacoes(alvo if alvo.is_dir() else alvo.parent, RAIZ)
            if not any(chave == relativo or chave.startswith(relativo + "/") for chave in achados):
                problemas.append(f"{relativo}: isento e já não importa toolkit nenhum")
        self.assertEqual([], problemas)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
