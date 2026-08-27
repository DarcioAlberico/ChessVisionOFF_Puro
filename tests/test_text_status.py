"""O plano de texto conferido contra o disco (S-178 a S-216).

**O defeito que isto evita.** A `docs/SPEC_TEXTO.md` marca cada item com `⬜ planejada`,
`◐ parcial` ou `✅ implementada`. Sem trava, essas marcas envelhecem exatamente como os doze
números que a S-135 encontrou errados ao mesmo tempo: alguém entrega metade de um item, marca
`✅`, e três semanas depois o documento descreve um programa que não existe.

Aqui a marca do documento é comparada com o que as sondas acham no disco, e discordar faz a suíte
falhar nomeando o item. É a mesma ideia da S-134 — documentação não tem compilador; o que ela tem
é um teste.

**Estes testes não medem o plano.** Eles medem a coerência entre três coisas que precisam
concordar: o manifesto em `text_status.py`, as seções da spec, e o disco. Se o plano for mudado,
os três mudam juntos ou a suíte avisa.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from chess_diagram_ocr import text_status
from chess_diagram_ocr.cli import text_status as cli

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / text_status.SPEC
ROADMAP = RAIZ / text_status.ROADMAP


class ManifestoTests(unittest.TestCase):
    """O manifesto é a fonte do comando; um erro aqui envenena tudo o que vem depois."""

    def test_os_itens_sao_contiguos_e_unicos(self) -> None:
        numeros = [int(item.id.split("-")[1]) for item in text_status.MANIFESTO]
        self.assertEqual(sorted(set(numeros)), numeros, "id repetido ou fora de ordem no manifesto.")
        self.assertEqual(list(range(numeros[0], numeros[-1] + 1)), numeros, "há buraco na numeração.")

    def test_toda_fase_do_manifesto_tem_titulo(self) -> None:
        fases = {item.fase for item in text_status.MANIFESTO}
        self.assertEqual(set(), fases - set(text_status.TITULO_DA_FASE))

    def test_todo_item_tem_pelo_menos_uma_sonda(self) -> None:
        sem_sonda = [item.id for item in text_status.MANIFESTO if not item.sondas]
        self.assertEqual([], sem_sonda, "Item sem sonda é item que nunca sai de pendente.")

    def test_toda_sonda_tem_forma_conhecida(self) -> None:
        """Uma sonda com erro de digitação responderia 'não existe' para sempre, calada.

        É a mesma família de defeito do `folder_to_char` que devolvia `"?"`: o silêncio é
        indistinguível do caso legítimo, e o item ficaria eternamente pendente sem motivo visível.
        """
        for item in text_status.MANIFESTO:
            for sonda in item.sondas:
                with self.subTest(sonda=sonda):
                    text_status.sonda_atendida(sonda, RAIZ)

    def test_sonda_desconhecida_levanta(self) -> None:
        with self.assertRaises(text_status.SondaInvalida):
            text_status.sonda_atendida("inventada:coisa", RAIZ)
        with self.assertRaises(text_status.SondaInvalida):
            text_status.sonda_atendida("simbolo:modulo_sem_nome", RAIZ)


class SpecEManifestoTests(unittest.TestCase):
    """A spec e o manifesto descrevem o mesmo plano, ou não descrevem plano nenhum."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.texto = SPEC.read_text(encoding="utf-8")
        cls.marcado = text_status.marcacoes_da_spec(RAIZ)

    def test_todo_item_do_manifesto_tem_secao_na_spec(self) -> None:
        ausentes = [item.id for item in text_status.MANIFESTO if item.id not in self.marcado]
        self.assertEqual([], ausentes, "Item no manifesto sem seção em docs/SPEC_TEXTO.md.")

    def test_toda_secao_da_spec_esta_no_manifesto(self) -> None:
        """O sentido inverso: um item especificado que o comando não conhece é invisível."""
        conhecidos = {item.id for item in text_status.MANIFESTO}
        sobrando = sorted(set(self.marcado) - conhecidos)
        self.assertEqual([], sobrando, "Seção na spec que o manifesto não conhece.")

    def test_o_cabecalho_de_toda_secao_traz_uma_marcacao(self) -> None:
        """`## S-NNN · titulo` sem marcação é o estado em que ninguém sabe se aquilo existe."""
        cabecalhos = re.findall(r"^## (S-\d{3}) .*$", self.texto, flags=re.MULTILINE)
        sem_marca = [ident for ident in cabecalhos if ident not in self.marcado]
        self.assertEqual([], sem_marca, "Seção sem ⬜/◐/✅ no cabeçalho.")

    def test_toda_secao_tem_criterio_de_aceite_e_sonda(self) -> None:
        """Item sem critério de aceite é intenção; sem sonda, é intenção que ninguém confere."""
        blocos = re.split(r"^## S-\d{3} ", self.texto, flags=re.MULTILINE)[1:]
        faltando = []
        for bloco in blocos:
            ident = bloco.split(" ", 1)[0] if bloco[:5].startswith("S-") else bloco[:5]
            for exigido in ("**Critério de aceite.**", "**Testes.**", "**Sonda.**"):
                if exigido not in bloco:
                    faltando.append(f"{ident}: falta {exigido}")
        self.assertEqual([], faltando)

    def test_a_sonda_escrita_na_spec_e_a_do_manifesto(self) -> None:
        """Duas listas de sonda que divergem fazem o documento mentir sobre o próprio verificador."""
        blocos = dict(
            zip(
                re.findall(r"^## (S-\d{3}) ", self.texto, flags=re.MULTILINE),
                re.split(r"^## S-\d{3} ", self.texto, flags=re.MULTILINE)[1:],
                strict=True,
            )
        )
        divergentes = []
        for item in text_status.MANIFESTO:
            trecho = blocos.get(item.id, "")
            depois = trecho.split("**Sonda.**", 1)
            if len(depois) < 2:
                continue
            escritas = set(re.findall(r"`([a-z]+:[^`]+)`", depois[1].split("---", 1)[0]))
            if escritas != set(item.sondas):
                divergentes.append(f"{item.id}: spec {sorted(escritas)} != manifesto {sorted(item.sondas)}")
        self.assertEqual([], divergentes)


class SpecEDiscoTests(unittest.TestCase):
    """A trava principal: o que o documento afirma e o que o disco tem.

    Um `✅ implementada` cuja sonda não acha nada é o defeito que esta suíte existe para pegar. O
    caso inverso -- código escrito e cabeçalho não atualizado -- também falha, porque a spec
    desatualizada é a que ninguém volta a confiar.
    """

    def test_a_marcacao_da_spec_corresponde_ao_disco(self) -> None:
        resultados = text_status.verificar(RAIZ)
        marcado = text_status.marcacoes_da_spec(RAIZ)

        # **Sonda de artefato não-versionado não vale como divergência (S-327).** As sondas são
        # de dois tipos: `simbolo:` pergunta ao código, que vem no clone, e `arquivo:` pergunta
        # ao disco -- e alguns dos arquivos que ela procura são `models/*.pt`, que o
        # `.gitignore` mantém fora. Num clone limpo, a S-182 aparecia como "parcial" contra uma
        # spec que diz "implementada", e o teste falhava afirmando que o documento mentia sobre
        # um item que **está** entregue: o que faltava era o binário, não o código.
        #
        # Foi a primeira execução da CI num ramo de trabalho (S-296) que mostrou isso. É a mesma
        # regra que o CONTRIBUTING já escreve para `data/samples/`: teste que depende de dado
        # não-versionado pula, não falha -- e aqui o pulo é por sonda, para o resto do item
        # continuar sendo cobrado.
        ausentes = {
            resultado.item.id
            for resultado in resultados
            for sonda in resultado.faltando
            if sonda.startswith("arquivo:") and not (RAIZ / sonda.removeprefix("arquivo:")).exists()
        }
        todas = cli._divergencias(resultados, marcado)
        divergencias = [linha for linha in todas if linha.split(":")[0] not in ausentes]

        self.assertEqual(
            [],
            divergencias,
            "Atualize o cabeçalho da seção em docs/SPEC_TEXTO.md, ou entregue o que ele afirma. "
            "`cvoff-texto-status --sondas` mostra qual sonda está faltando.",
        )
        # O pulo vem **depois** da afirmação, e só quando o filtro de fato escondeu alguma coisa:
        # assim o resto do item continua cobrado, e uma execução que não pôde olhar tudo não se
        # anuncia como se tivesse olhado.
        if len(todas) != len(divergencias):
            self.skipTest(f"artefato não-versionado ausente: {', '.join(sorted(ausentes))}")


class RoadmapTests(unittest.TestCase):
    """O roadmap é onde se lê o porquê; um plano cujas fases não batem com a spec não se lê."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.texto = ROADMAP.read_text(encoding="utf-8")

    def test_toda_fase_aparece_no_roadmap(self) -> None:
        ausentes = [fase for fase in text_status.TITULO_DA_FASE if f"Fase {fase} " not in self.texto]
        self.assertEqual([], ausentes)

    def test_o_roadmap_nao_traz_secao_de_item(self) -> None:
        """Item mora na spec, e `tests/test_docs.py` cobra isso pela tabela de faixas do README.

        Um `## S-NNN` aqui faria a S-NN aparecer em dois arquivos, e a suíte de documentação
        passaria a acusar "seção no arquivo errado" -- com razão.
        """
        secoes = re.findall(r"^#{1,4} (S-\d{1,3})\b", self.texto, flags=re.MULTILINE)
        self.assertEqual([], secoes)

    def test_o_roadmap_declara_o_comando_de_status(self) -> None:
        self.assertIn("cvoff-texto-status", self.texto)


class ComandoTests(unittest.TestCase):
    """O comando roda, e não depende de nenhum extra para rodar."""

    def test_a_saida_de_texto_lista_todas_as_fases(self) -> None:
        resultados = text_status.verificar(RAIZ)
        saida = cli._texto(resultados, com_sondas=False, marcado=text_status.marcacoes_da_spec(RAIZ))
        for fase in text_status.TITULO_DA_FASE:
            self.assertIn(f"Fase {fase} —", saida)

    def test_o_codigo_de_saida_e_zero_com_tudo_pendente(self) -> None:
        """Um plano por fazer é o estado normal de um plano. Falhar aqui ensina a ignorar."""
        self.assertEqual(0, cli.main(["--json"]))

    def test_o_exigir_falha_no_item_pendente(self) -> None:
        pendentes = [r.item.id for r in text_status.verificar(RAIZ) if r.estado != "feito"]
        if not pendentes:  # pragma: no cover - plano inteiro entregue
            self.skipTest("nenhum item pendente: o plano acabou")
        self.assertEqual(1, cli.main(["--json", "--exigir", pendentes[0]]))

    def test_o_exigir_falha_em_item_que_nao_existe(self) -> None:
        self.assertEqual(1, cli.main(["--json", "--exigir", "S-999"]))

    def test_o_console_cp1252_recebe_ascii_em_vez_de_excecao(self) -> None:
        """`print("⬜")` num `cmd.exe` cp1252 levanta, e o comando inteiro cai.

        Não é defeito cosmético: é o console padrão da máquina em que este projeto roda. O
        `configure_logging` tenta reconfigurar para UTF-8 primeiro; este é o que sobra quando ele
        não consegue.
        """

        class FluxoLatino:
            encoding = "cp1252"

        self.assertTrue(cli._so_ascii(FluxoLatino()))  # type: ignore[arg-type]

        class FluxoUtf8:
            encoding = "utf-8"

        self.assertFalse(cli._so_ascii(FluxoUtf8()))  # type: ignore[arg-type]

    def test_a_saida_ascii_nao_traz_nenhum_simbolo_fora_do_latin1(self) -> None:
        resultados = text_status.verificar(RAIZ)
        saida = cli._texto(resultados, com_sondas=True, marcado={}, ascii_puro=True)
        # O título de um item pode ter acento (cp1252 encoda); o que não pode passar são os
        # três símbolos de estado e o travessão.
        for proibido in (*text_status.SIMBOLO_DE_ESTADO.values(), "—"):
            self.assertNotIn(proibido, saida)
        saida.encode("cp1252")

    def test_a_fase_filtra(self) -> None:
        so_25 = text_status.verificar(RAIZ, fase=25)
        self.assertTrue(so_25)
        self.assertEqual({25}, {r.item.fase for r in so_25})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
