"""A documentação conferida contra o disco (S-134).

**O defeito que isto evita.** A spec deste projeto está em cinco arquivos, e não havia índice.
O `CONTRIBUTING` mandava registrar mudança de fase no `ROADMAP.md`, que fecha na Fase 6. O
resultado mecânico foi a S-76 e a S-77 ficarem **três meses em produção sem spec em documento
nenhum** — entregues em 2026-08-14, caindo na fenda entre o `SPEC_FASE7` (que parava em S-75) e
o `ANALISE_DETECCAO` (que começa em S-78), citadas de passagem quatro vezes e especificadas em
lugar algum.

Documentação não tem compilador. O que ela tem é isto: uma suíte que falha quando alguém entrega
uma S-NN e esquece de escrevê-la, ou escreve no arquivo errado, ou acrescenta um documento que
o índice não menciona.

**Por que a fonte é o `git log`.** O critério é "entregue", e a única definição não-opinativa de
entregue é ter commit. Um item que existe só no roadmap ainda não é dívida de documentação; um
que já está no `main` é.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
README = RAIZ / "README.md"

SECAO = re.compile(r"^#{1,4} (S-\d{1,3})\b")
"""Uma seção de item: `## S-95 · ...` ou `### S-78 · ...`. O nível varia entre os arquivos."""

LINHA_DA_TABELA = re.compile(r"^>?\s*\|\s*(S-\d.*?)\s*\|\s*(.*?)\s*\|\s*$")
"""Uma linha da tabela "faixa de itens → arquivo", com ou sem o `>` de citação."""

ARQUIVOS_DE_MEDICAO = {"EXPERIMENTS.md", "EXPERIMENTS_FASE7.md", "BASELINE.md", "ROADMAP_FASE7.md"}
"""Trazem seções `S-NN` que **não** são spec: são o que foi medido daquele item.

Ficam de fora da tabela de faixas de propósito -- exigir que a medição da S-26 morasse no mesmo
arquivo que a spec dela juntaria dois documentos que existem separados por bom motivo. Elas
contam para "o item tem seção em algum lugar"? Não: uma medição sem critério de aceite é
justamente o que a S-133 veio consertar.
"""


def _numero(identificador: str) -> int:
    return int(identificador.split("-")[1])


def _rotulo(numero: int) -> str:
    return f"S-{numero:02d}"


def itens_entregues() -> dict[int, str]:
    """`S-NN` citado em `git log --oneline` → a linha do commit que o entregou.

    Devolve `{}` quando não há git ou o histórico é raso, e quem chama pula o teste. **Um
    histórico raso mentiria em silêncio**: com `fetch-depth: 1` o log tem um commit, o conjunto
    sai quase vazio e o teste passa sem ter olhado nada. O `.github/workflows/ci.yml` usa
    `fetch-depth: 0` por causa disto, e o limiar abaixo é o que garante que isso continue.
    """
    try:
        resultado = subprocess.run(
            ["git", "log", "--oneline", "--no-decorate"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:  # pragma: no cover - maquina sem git no PATH
        return {}
    if resultado.returncode != 0:  # pragma: no cover - checkout sem .git
        return {}

    linhas = [linha for linha in resultado.stdout.splitlines() if linha.strip()]
    if len(linhas) < 50:  # pragma: no cover - clone raso
        return {}

    entregues: dict[int, str] = {}
    for linha in linhas:
        for achado in re.finditer(r"S-(\d{1,3})\b", linha):
            entregues.setdefault(int(achado.group(1)), linha)
    return entregues


def secoes_por_arquivo() -> dict[str, set[int]]:
    return {
        arquivo.name: {
            _numero(m.group(1))
            for linha in arquivo.read_text(encoding="utf-8").splitlines()
            if (m := SECAO.match(linha))
        }
        for arquivo in sorted(DOCS.glob("*.md"))
    }


def faixas_declaradas(texto: str) -> dict[int, str]:
    """A tabela "faixa de itens → arquivo" de um documento, achatada em `numero → arquivo`.

    Aceita `S-37 a S-77` e `S-78 a S-82, S-143` na mesma célula: a faixa da detecção não é
    contígua de propósito, e o formato precisa dizer isso sem virar prosa.
    """
    declarado: dict[int, str] = {}
    for linha in texto.splitlines():
        casamento = LINHA_DA_TABELA.match(linha)
        if casamento is None:
            continue
        celula_itens, celula_arquivo = casamento.groups()
        arquivo = re.search(r"([A-Z_0-9]+\.md)", celula_arquivo)
        if arquivo is None:
            continue
        for parte in celula_itens.split(","):
            limites = [int(n) for n in re.findall(r"S-(\d{1,3})", parte)]
            if len(limites) == 2:
                numeros = range(limites[0], limites[1] + 1)
            elif len(limites) == 1:
                numeros = range(limites[0], limites[0] + 1)
            else:
                continue
            for numero in numeros:
                declarado[numero] = arquivo.group(1)
    return declarado


class ItemEntregueTemSpecTests(unittest.TestCase):
    """Entregar uma S-NN sem documentá-la faz a suíte falhar, nomeando o item e o commit."""

    def setUp(self) -> None:
        self.entregues = itens_entregues()
        if not self.entregues:
            self.skipTest("sem histórico de git utilizável (clone raso ou sem .git)")
        self.secoes = secoes_por_arquivo()

    def test_todo_item_entregue_tem_secao_em_algum_doc(self) -> None:
        com_secao: set[int] = set()
        for arquivo, numeros in self.secoes.items():
            if arquivo not in ARQUIVOS_DE_MEDICAO:
                com_secao |= numeros

        faltando = sorted(set(self.entregues) - com_secao)
        self.assertEqual(
            [],
            [f"{_rotulo(n)} — entregue em: {self.entregues[n]}" for n in faltando],
            "Item entregue sem seção em docs/*.md. Escreva a seção no arquivo que a tabela "
            '"Onde mora a spec de cada item" do README indica para essa faixa.',
        )

    def test_a_secao_esta_no_arquivo_que_o_indice_declara(self) -> None:
        """Ter seção não basta: escrevê-la no arquivo errado recria a fenda de outro jeito."""
        declarado = faixas_declaradas(README.read_text(encoding="utf-8"))
        self.assertTrue(declarado, "O README perdeu a tabela de faixas.")

        fora_do_lugar = []
        for arquivo, numeros in sorted(self.secoes.items()):
            if arquivo in ARQUIVOS_DE_MEDICAO:
                continue
            for numero in sorted(numeros):
                esperado = declarado.get(numero)
                if esperado is not None and esperado != arquivo:
                    fora_do_lugar.append(f"{_rotulo(numero)} está em {arquivo}, e o índice diz {esperado}")

        self.assertEqual([], fora_do_lugar)

    def test_o_indice_nao_declara_faixa_sem_dono(self) -> None:
        """Uma faixa declarada que nenhum item ocupa é índice apontando para o vazio."""
        declarado = faixas_declaradas(README.read_text(encoding="utf-8"))
        por_arquivo: dict[str, list[int]] = {}
        for numero, arquivo in declarado.items():
            por_arquivo.setdefault(arquivo, []).append(numero)

        vazios = [arquivo for arquivo in por_arquivo if not (DOCS / arquivo).exists()]
        self.assertEqual([], vazios, "O índice cita um arquivo que não existe em docs/.")


class IndiceDoReadmeTests(unittest.TestCase):
    """Todo `docs/*.md` aparece no índice do README, e a tabela de faixas é a mesma em todos."""

    def test_todo_documento_aparece_no_readme(self) -> None:
        texto = README.read_text(encoding="utf-8")
        ausentes = [
            arquivo.name
            for arquivo in sorted(DOCS.glob("*.md"))
            if arquivo.relative_to(RAIZ).as_posix() not in texto
        ]
        self.assertEqual(
            [],
            ausentes,
            "Documento em docs/ que o índice do README não menciona. Quem procura onde está a "
            "spec da entrega X lê o índice, não o grep.",
        )

    def test_a_tabela_de_faixas_e_a_mesma_em_todos_os_documentos_que_a_trazem(self) -> None:
        """Cinco cópias da tabela; divergir entre elas seria pior que não tê-la.

        A cópia é deliberada: quem abre o `SPEC_FASE7` direto não passa pelo README, e mandá-lo
        procurar o índice noutro arquivo é o mesmo obstáculo que criou a fenda. O preço é este
        teste.
        """
        referencia = faixas_declaradas(README.read_text(encoding="utf-8"))
        self.assertTrue(referencia, "O README perdeu a tabela de faixas.")

        divergentes = []
        copias = 0
        for arquivo in sorted(DOCS.glob("*.md")):
            declarado = faixas_declaradas(arquivo.read_text(encoding="utf-8"))
            if not declarado:
                continue
            copias += 1
            if declarado != referencia:
                diferenca = sorted(
                    _rotulo(n)
                    for n in set(declarado) ^ set(referencia)
                    | {n for n in set(declarado) & set(referencia) if declarado[n] != referencia[n]}
                )
                divergentes.append(f"{arquivo.name}: difere do README em {', '.join(diferenca)}")

        self.assertEqual([], divergentes)
        self.assertGreaterEqual(copias, 5, "A tabela sumiu de algum dos cinco documentos de spec.")


if __name__ == "__main__":
    unittest.main()
