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
from fnmatch import fnmatch
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
        """Seis cópias em `docs/`, mais o README que serve de referência; divergir entre elas
        seria pior que não tê-la.

        A cópia é deliberada: quem abre o `SPEC_FASE7` direto não passa pelo README, e mandá-lo
        procurar o índice noutro arquivo é o mesmo obstáculo que criou a fenda. O preço é este
        teste.

        **O README não é mais uma cópia, é a referência**, e isso muda como a falha aparece:
        editar os seis documentos e esquecer o README não acusa um arquivo, acusa **os seis de
        uma vez** -- e o README, que é o único errado, não entra na lista. É tudo ou nada nos
        sete.

        O piso dizia `5` quando os documentos já eram seis (corrigido em 2026-08-23, junto com o
        "Cinco cópias" acima). Um piso um abaixo da realidade tolera exatamente o que ele existe
        para pegar: um documento perder a tabela sem que nada fale. Subir o piso é seguro --
        documento novo que traga a tabela só faz a contagem crescer.
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
        self.assertGreaterEqual(copias, 6, "A tabela sumiu de algum dos seis documentos de spec.")


TOLERANCIA = 0.10
"""Quanto um número citado pode ficar para trás do disco antes de a suíte falhar (S-135).

**Por que tolerância e não igualdade.** `labels.csv`, `data/samples/` e `PDF/` crescem a cada
gesto de uso: com igualdade exata, salvar uma amostra deixaria a suíte vermelha, e o time
aprenderia a ignorar este arquivo — que é o oposto do que ele existe para fazer.

**Por que 10%, e não 50%.** As doze divergências que a S-135 encontrou estavam todas acima
disso: `labels.csv` citava 3.313 contra 3.936 (15,8%), os PNGs 3.200 contra 3.935 (18,7%), o
acervo 27 livros contra 39 (30,8%), a base 9,7 GB contra 18,9 (49%). Dez por cento passa em
crescimento de uso e falha em número esquecido, que é exatamente a divisão que se quer.

De brinde, ela absorve a confusão GB↔GiB (7,4%), que neste projeto já fez alguém "corrigir" um
número que estava certo.
"""


def chaves_da_secao(secao: str) -> list[str]:
    """As chaves de uma tabela do `pyproject.toml`, sem depender de um leitor de TOML.

    São só duas seções — `[project.scripts]` e `[project.optional-dependencies]` — e as duas
    são listas de `chave = ...` sem aninhamento, então um leitor de dez linhas basta.

    **O `tomllib` resolveria, e não serve**: ele é 3.11+ e este projeto exige 3.10. O `tomli`
    que existe no ambiente vem de carona com o `mypy` e não está declarado em lugar nenhum —
    depender do que ninguém declarou é como um teste passa hoje e some amanhã, que é a mesma
    família de defeito que a S-128 consertou na CI.
    """
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    dentro = False
    chaves: list[str] = []
    for linha in texto.splitlines():
        despida = linha.strip()
        if despida.startswith("["):
            dentro = despida == f"[{secao}]"
            continue
        if not dentro:
            continue
        achado = re.match(r"([A-Za-z0-9_-]+)\s*=", despida)
        if achado:
            chaves.append(achado.group(1))
    return chaves


def _citado(texto: str, padrao: str) -> float:
    """O primeiro número que casa com `padrao`, em português: `3.936` e `18,9`."""
    achado = re.search(padrao, texto)
    assert achado is not None, f"o documento perdeu o trecho: {padrao}"
    return float(achado.group(1).replace(".", "").replace(",", "."))


def _perto(caso: unittest.TestCase, citado: float, real: float, o_que: str) -> None:
    if real == 0:  # pragma: no cover - repositorio sem o artefato
        caso.skipTest(f"{o_que} não existe neste checkout")
    desvio = abs(citado - real) / real
    caso.assertLessEqual(
        desvio,
        TOLERANCIA,
        f"{o_que}: o documento diz {citado:g} e o disco tem {real:g} "
        f"({desvio:.1%} de diferença, o limite é {TOLERANCIA:.0%}).",
    )


class NumerosVivosTests(unittest.TestCase):
    """Nenhum número citado em documento diverge do disco sem que a suíte falhe (S-135).

    É o critério de saída da Fase 19, e ele existe porque a alternativa foi medida: doze
    afirmações de `README.md` e `ARCHITECTURE.md` estavam erradas ao mesmo tempo, entre elas um
    módulo que não existe desde a S-54 e um artefato que este repositório nunca teve.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text(encoding="utf-8")
        cls.arquitetura = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")

    def test_o_labels_csv_citado_bate_com_o_disco(self) -> None:
        alvo = RAIZ / "data" / "labels.csv"
        if not alvo.exists():
            self.skipTest("data/labels.csv não existe neste checkout")
        real = len(alvo.read_text(encoding="utf-8").splitlines()) - 1
        citado = _citado(self.arquitetura, r"o `labels\.csv` tem \*\*([\d.]+)\*\* linhas")
        _perto(self, citado, real, "linhas do labels.csv")

    def test_os_pngs_citados_batem_com_o_disco(self) -> None:
        pasta = RAIZ / "data" / "samples"
        if not pasta.exists():
            self.skipTest("data/samples/ não existe neste checkout")
        real = sum(1 for _ in pasta.rglob("*.png"))
        citado = _citado(self.readme, r"([\d.]+) PNGs de tabuleiros")
        _perto(self, citado, real, "PNGs em data/samples")

    def test_o_acervo_citado_bate_com_a_pasta_PDF(self) -> None:
        """O número que a S-135 pegou mais desatualizado: 27 contra 39 livros."""
        pasta = RAIZ / "PDF"
        if not pasta.exists():
            self.skipTest("PDF/ não existe neste checkout")
        real = sum(1 for _ in pasta.glob("*.pdf"))
        citado = _citado(self.readme, r"Hoje o acervo tem (\d+) PDFs")
        _perto(self, citado, real, "PDFs em PDF/")

    def test_a_base_de_partidas_citada_bate_com_o_disco(self) -> None:
        pasta = RAIZ / "pgn_database"
        if not pasta.exists():
            self.skipTest("pgn_database/ não existe neste checkout")
        real = sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / 10**9
        citado = _citado(self.readme, r"as duas gigabases medidas aqui tem ([\d,]+) GB")
        _perto(self, citado, real, "tamanho de pgn_database/ em GB")

    def test_todo_modulo_citado_como_interface_existe(self) -> None:
        """Pega o `app_streamlit.py`, que a ARCHITECTURE descreveu por três meses depois da S-54."""
        citados = set(re.findall(r"`(app_\w+\.py)`", self.arquitetura))
        self.assertTrue(citados, "a ARCHITECTURE perdeu a menção às interfaces.")
        ausentes = sorted(nome for nome in citados if not (RAIZ / nome).exists())
        self.assertEqual([], ausentes, "A ARCHITECTURE descreve um módulo que não existe.")

    def test_a_tabela_de_persistencia_lista_o_que_data_tem(self) -> None:
        """Nos dois sentidos: artefato sem linha, e linha apontando para o que não existe.

        A tabela já esteve com 8 dos 16 artefatos, o `splits.csv` em duas linhas e uma linha
        para o `provenance_index.jsonl`, que este repositório nunca teve.
        """
        citados = set(re.findall(r"`(data/[\w./<>-]+)`", self.arquitetura))
        pasta = RAIZ / "data"
        if not pasta.exists():
            self.skipTest("data/ não existe neste checkout")

        no_disco = {
            f"data/{item.name}" + ("/" if item.is_dir() else "")
            for item in pasta.iterdir()
            if ".bak" not in item.name
        }
        def coberto(caminho: str) -> bool:
            # Uma pasta conta como listada quando a tabela descreve o que mora dentro dela --
            # `data/gallery/` está em duas linhas, uma por tipo de arquivo, e exigir uma
            # terceira linha para a pasta em si seria ruído.
            nu = caminho.rstrip("/")
            if nu in citados or any(citado.startswith(f"{nu}/") for citado in citados):
                return True
            # E um `<placeholder>` no meio do **nome** conta como a familia dele. A metade de
            # tras deste teste ja pulava esses caminhos; a metade da frente nao os entendia, e
            # o sintoma foi um `games_positions__PGN_Database.sqlite` cobrado como artefato sem
            # linha quando a linha existia -- escrita como `games_positions__<bases>.sqlite`,
            # que e a unica forma de descrever um arquivo por conjunto de bases.
            return any(
                "<" in citado and fnmatch(nu, re.sub(r"<[^>]+>", "*", citado))
                for citado in citados
            )

        sem_linha = sorted(caminho for caminho in no_disco if not coberto(caminho))
        self.assertEqual([], sem_linha, "Artefato em data/ que a tabela de persistência não lista.")

        # A metade de tras -- "a linha aponta para o que nao existe" -- so pode ser cobrada
        # onde o arquivo *poderia* existir. Num clone limpo, `data/` tem so o que o git
        # rastreia: `settings.json`, `review_queue.json` e mais oito sao criados pelo uso, e
        # cobrar a existencia deles ali transformaria o guarda num "a CI nunca rodou o
        # programa". Foi exatamente assim que ele reprovou a CI e passou aqui.
        #
        # A linha marcada **sim** e outra coisa: ela e versionada, entao a ausencia dela e
        # defeito em qualquer checkout.
        versionados = {
            caminho
            for caminho, marca in re.findall(r"^\| `(data/[\w./<>-]+)` \|[^|]*\| ([^|]*)\|", self.arquitetura, re.M)
            if marca.strip().lower().startswith(("sim", "**sim**"))
        }
        sumidos = sorted(c for c in versionados if "<" not in c and not (RAIZ / c).exists())
        self.assertEqual([], sumidos, "A tabela marca como versionado um arquivo que não está no disco.")

        def existe(caminho: str) -> bool:
            return (RAIZ / caminho).exists() or (RAIZ / caminho.rstrip("/")).exists()

        sob_demanda = set(re.findall(r"`(data/[\w./-]+)`[^|]*\|[^|]*\|[^|]*sob demanda", self.arquitetura))
        de_uso = {c for c in citados - versionados if "<" not in c and c not in sob_demanda}
        # O sinal de "a pasta esta em uso" sao os **arquivos**, nao as pastas: `data/samples/`
        # vem no clone por causa do `.gitkeep` e existiria mesmo num checkout que nunca rodou
        # o programa.
        if not any(existe(caminho) for caminho in de_uso if not caminho.endswith("/")):
            # Nenhum artefato de uso no disco: e um clone que nunca rodou o programa, e ali a
            # ausencia nao prova nada. Com pelo menos um presente, a pasta esta em uso e a
            # linha que continua sem arquivo e suspeita -- foi assim que o
            # `provenance_index.jsonl`, que este repositorio nunca teve, apareceu.
            self.skipTest("nenhum artefato de uso em data/: um clone limpo não prova ausência.")

        fantasmas = sorted(caminho for caminho in de_uso if not existe(caminho))
        self.assertEqual(
            [],
            fantasmas,
            "A tabela cita um caminho que não existe e não está marcado como sob demanda.",
        )

    def test_as_fontes_do_lado_a_jogar_batem_com_o_Literal(self) -> None:
        """A tabela do README dizia "três" enquanto `semantics.py` declarava oito."""
        from typing import get_args

        from chess_diagram_ocr.semantics import SideSource

        valores = set(get_args(SideSource))
        citado = int(_citado(self.readme, r"diz \*\*qual das (\d+)\*\* foi"))
        self.assertEqual(len(valores), citado, "O README e o `Literal` discordam na contagem.")

        na_tabela = set(re.findall(r"^\| `([a-z-]+)` \| ", self.readme, flags=re.MULTILINE))
        self.assertEqual(
            set(),
            valores - na_tabela,
            "Valor de `SideSource` que a tabela do README não explica.",
        )

    def test_todo_extra_do_pyproject_aparece_no_README(self) -> None:
        """Pega o `second-opinion`: um botão na tela, 232,8 MiB de clone, e zero menções."""
        extras = chaves_da_secao("project.optional-dependencies")
        self.assertTrue(extras, "o pyproject perdeu a seção de extras (ou o leitor quebrou).")
        ausentes = sorted(extra for extra in extras if extra not in self.readme)
        self.assertEqual([], ausentes, "Extra do pyproject que o README não menciona.")

    def test_o_numero_de_comandos_citado_bate_com_project_scripts(self) -> None:
        """Dizia "os três comandos abaixo", e a lista tinha quinze."""
        comandos = chaves_da_secao("project.scripts")
        self.assertTrue(comandos, "o pyproject perdeu a seção de comandos (ou o leitor quebrou).")
        citado = int(_citado(self.readme, r"\*\*(\d+) comandos\*\* ficam disponiveis"))
        self.assertEqual(len(comandos), citado)

    def test_o_bundle_citado_bate_com_o_que_o_build_gravou(self) -> None:
        """O README publicava 5.247 arquivos de um build que tinha 4.723 (S-135)."""
        import json

        metricas_json = DOCS / "metrics" / "bundle.json"
        if not metricas_json.exists():
            self.skipTest("docs/metrics/bundle.json ainda não foi gerado por um build")
        metricas = json.loads(metricas_json.read_text(encoding="utf-8"))

        citado_mb = int(_citado(self.readme, r"\*\*([\d.]+) MB, [\d.]+ arquivos\*\*"))
        citado_arquivos = int(_citado(self.readme, r"\*\*[\d.]+ MB, ([\d.]+) arquivos\*\*"))
        self.assertEqual((metricas["mb"], metricas["arquivos"]), (citado_mb, citado_arquivos))

    def test_o_bundle_obsoleto_se_diz_obsoleto(self) -> None:
        """Um número certo sobre um build que já não existe engana igual a um número errado."""
        import json

        metricas_json = DOCS / "metrics" / "bundle.json"
        if not metricas_json.exists():
            self.skipTest("docs/metrics/bundle.json ainda não foi gerado por um build")
        metricas = json.loads(metricas_json.read_text(encoding="utf-8"))
        if not metricas.get("obsoleto"):
            return
        self.assertIn(
            "obsoleta",
            self.readme,
            "As métricas do bundle estão marcadas como obsoletas e o README não avisa.",
        )

    # ------------------------------------------ o placar de uma fase envelhece igual (2026-08-18)

    def test_o_placar_da_fase_6_nao_diz_nao_iniciado_sobre_o_que_existe(self) -> None:
        """**A décima-segunda guarda, e ela nasceu de um achado.** O critério de saída da Fase 6
        ficou parado em 2026-07-27 dizendo *"executável rodando em máquina sem Python: não
        iniciado"* -- sobre o bundle que a S-55 entregou, a S-127 instrumentou e a S-135 mediu.

        A guarda é a mesma ideia dos onze números do README: se o artefato existe no disco, o
        documento não pode continuar dizendo que ele não existe.
        """
        if not (RAIZ / "packaging" / "cvoff.spec").exists():
            self.skipTest("packaging/cvoff.spec não existe neste checkout")
        roadmap = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
        criterio = roadmap.split("## Fase 6", 1)[1].split("## Fase 7", 1)[0]

        # A **última** celula da linha, e nao a secao inteira: a coluna do meio guarda o estado
        # de 2026-07-27 de proposito, e cobrar "nao iniciado" ali apagaria o registro de que o
        # placar envelheceu -- que e justamente o que este item existe para mostrar.
        linha = next(
            (li for li in criterio.splitlines() if li.startswith("| executável rodando")),
            None,
        )
        self.assertIsNotNone(linha, "a linha do executável sumiu do critério de saída da Fase 6")
        assert linha is not None
        hoje = linha.rstrip("|").rsplit("|", 1)[-1]
        self.assertNotIn(
            "não iniciado",
            hoje,
            "A Fase 6 diz que o empacotamento não começou, e `packaging/cvoff.spec` está no disco.",
        )

    def test_as_linhas_da_janela_citadas_na_fase_6_batem_com_a_catraca(self) -> None:
        """O 651 do placar original era honesto quando foi escrito, e virou falso sem que nada
        avisasse -- o arquivo dobrou (S-136). O número citado passa a sair do mesmo lugar que a
        catraca de `test_packaging.py` cobra."""
        janela = RAIZ / "app_tkinter.py"
        if not janela.exists():
            self.skipTest("app_tkinter.py não existe neste checkout")
        real = len(janela.read_text(encoding="utf-8").splitlines())
        roadmap = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
        criterio = roadmap.split("## Fase 6", 1)[1].split("## Fase 7", 1)[0]
        citado = _citado(criterio, r"\*\*([\d.]+)\*\*, e o arquivo dobrou")
        _perto(self, citado, real, "linhas de app_tkinter.py citadas na Fase 6")

    def test_o_placar_das_fases_bate_com_o_da_janela(self) -> None:
        """O quadro "Onde o projeto está" cita o mesmo número da catraca (2026-08-18).

        Ele é o texto que alguém lê para saber onde o projeto parou, e é por isso que ele é o
        primeiro a envelhecer -- foi exatamente o que aconteceu com o critério de saída da Fase
        6, que passou três semanas dizendo "não iniciado" sobre um `.exe` que rodava.
        """
        janela = RAIZ / "app_tkinter.py"
        if not janela.exists():
            self.skipTest("app_tkinter.py não existe neste checkout")
        real = len(janela.read_text(encoding="utf-8").splitlines())
        roadmap = (DOCS / "ROADMAP_FASE14.md").read_text(encoding="utf-8")
        # `chr(10) + "---" + chr(10)` e nao `"---"`: a propria tabela tem `|---|` nas
        # separadoras, e cortar ali deixaria o quadro sem as linhas que se quer conferir.
        quadro = roadmap.split("## Onde o projeto está", 1)[1]
        quadro = quadro.split(chr(10) + "---" + chr(10), 1)[0]
        citado = _citado(quadro, r"`app_tkinter\.py` em ([\d.]+) contra")
        _perto(self, citado, real, "linhas de app_tkinter.py no quadro das fases")


if __name__ == "__main__":
    unittest.main()
