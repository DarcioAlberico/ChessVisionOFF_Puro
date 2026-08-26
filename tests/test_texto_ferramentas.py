"""As ferramentas da Fase 41: alinhamento, corpo, tachado e caixa (S-259 a S-262).

O que estes testes travam é a metade que não precisa de janela -- e é onde as decisões estão. Cada
ferramenta é uma função pura sobre `DocumentoRico`, e o que se afirma aqui é o **alcance** de cada
uma: quem o alinhamento pega além do que foi selecionado (o parágrafo, e a figura dentro dele), o
que o corpo faz com um trecho que já está no limite, e o que a troca de caixa **não** toca.

**O caso que dá nome à fase.** Centralizar um parágrafo que contém um diagrama tem de centralizar o
diagrama junto -- e a marca `[Diagrama N]` é a única corrida do documento que recusa atributo, por
uma decisão da S-235 que continua certa para os outros nove. `rico.ATRIBUTOS_DA_MARCA` é a fronteira
que abre exatamente um, e os dois primeiros testes desta suíte são os que a mantêm exatamente um.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import documento, rico


def _doc(*corridas: rico.Corrida) -> rico.DocumentoRico:
    return rico.DocumentoRico(corridas=corridas)


def _texto(conteudo: str, *, bloco: int = rico.SEM_BLOCO, **atributos: object) -> rico.Corrida:
    return rico.Corrida(texto=conteudo, atributos=rico.Atributos(**atributos), bloco=bloco)  # type: ignore[arg-type]


def _marca(indice: int = 1, *, bloco: int = 0) -> rico.Corrida:
    return rico.Corrida(texto=f"[Diagrama {indice}]", tipo=rico.DIAGRAMA, bloco=bloco)


class ConjuntosFechadosTests(unittest.TestCase):
    """Como `ESTILOS` e `GRUPOS`: o conjunto é fechado, e o de fora levanta."""

    def test_os_alinhamentos_sao_quatro(self) -> None:
        self.assertEqual(rico.ALINHAMENTOS, ("esquerda", "centro", "direita", "justificado"))

    def test_alinhamento_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Atributos(alinhamento="ao_meio")
        with self.assertRaises(KeyError):
            rico.aplicar_alinhamento(rico.de_texto("texto"), 0, 5, "ao_meio")

    def test_as_caixas_sao_tres(self) -> None:
        self.assertEqual(rico.CAIXAS, ("alta", "baixa", "iniciais"))

    def test_caixa_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.mudar_caixa(rico.de_texto("texto"), 0, 5, "versalete")

    def test_corpo_fora_da_faixa_levanta(self) -> None:
        """Quem grampeia é o gesto (`corpo_no_limite`); o dado levanta -- ver o `__post_init__`."""
        with self.assertRaises(KeyError):
            rico.Atributos(corpo=rico.CORPO_MAXIMO + 1)
        with self.assertRaises(KeyError):
            rico.Atributos(corpo=rico.CORPO_MINIMO - 1)

    def test_o_limite_grampeia_dos_dois_lados(self) -> None:
        self.assertEqual(rico.corpo_no_limite(99), rico.CORPO_MAXIMO)
        self.assertEqual(rico.corpo_no_limite(-99), rico.CORPO_MINIMO)
        self.assertEqual(rico.corpo_no_limite(1), 1)


class AlinhamentoTests(unittest.TestCase):
    """S-259. O alcance é o parágrafo, e a figura dentro dele vai junto."""

    def test_alinhar_uma_palavra_alinha_o_paragrafo(self) -> None:
        """O bloco inteiro, e não o que foi selecionado: o mesmo alcance de `aplicar_estilo`."""
        doc = _doc(_texto("primeira parte ", bloco=0), _texto("segunda parte", bloco=0))
        alinhado = rico.aplicar_alinhamento(doc, 0, 8, rico.ALINHAMENTO_CENTRO)
        self.assertEqual({c.atributos.alinhamento for c in alinhado.corridas}, {"centro"})

    def test_o_paragrafo_vizinho_nao_e_tocado(self) -> None:
        doc = _doc(_texto("deste bloco", bloco=0), _texto("do outro", bloco=1))
        alinhado = rico.aplicar_alinhamento(doc, 0, 5, rico.ALINHAMENTO_DIREITA)
        self.assertEqual(alinhado.corridas[0].atributos.alinhamento, "direita")
        self.assertEqual(alinhado.corridas[1].atributos.alinhamento, "")

    def test_centralizar_o_paragrafo_centraliza_a_figura(self) -> None:
        """**O caso que dá nome à fase.** A marca do diagrama recebe o alinhamento -- e só ele."""
        doc = _doc(_texto("antes ", bloco=0), _marca(bloco=0), _texto(" depois", bloco=0))
        alinhado = rico.aplicar_alinhamento(doc, 0, 3, rico.ALINHAMENTO_CENTRO)
        marca = next(c for c in alinhado.corridas if c.e_diagrama)
        self.assertEqual(marca.atributos.alinhamento, "centro")

    def test_a_marca_continua_recusando_os_outros_atributos(self) -> None:
        """A regra da S-235 continua inteira: o que a marca aceita é `ATRIBUTOS_DA_MARCA`."""
        self.assertEqual(rico.ATRIBUTOS_DA_MARCA, frozenset({"alinhamento"}))
        doc = _doc(_marca(bloco=0))
        negrito = rico.aplicar(doc, 0, len(doc.para_texto()), negrito=True)
        self.assertFalse(negrito.corridas[0].atributos.negrito)

    def test_o_separador_nao_recebe_alinhamento(self) -> None:
        """Ele não é texto do livro nem figura: é o vão entre dois blocos."""
        doc = _doc(rico.Corrida(texto="\n\n", tipo=rico.SEPARADOR, bloco=0))
        alinhado = rico.aplicar_alinhamento(doc, 0, 2, rico.ALINHAMENTO_CENTRO)
        self.assertEqual(alinhado.corridas[0].atributos, rico.PADRAO)

    def test_alinhar_carimba_humano(self) -> None:
        """Escolha de quem escreve é correção sobre o que o motor entregou (S-239)."""
        doc = _doc(rico.Corrida(texto="lido do livro", bloco=0, procedencia="glifo"))
        alinhado = rico.aplicar_alinhamento(doc, 0, 4, rico.ALINHAMENTO_CENTRO)
        self.assertEqual(alinhado.corridas[0].procedencia, "humano")

    def test_esquerda_nao_e_o_mesmo_que_sem_alinhamento(self) -> None:
        """`""` é "ninguém escolheu"; `esquerda` é "alguém voltou atrás" -- e os dois sobrevivem."""
        doc = _doc(_texto("um parágrafo", bloco=0))
        centro = rico.aplicar_alinhamento(doc, 0, 2, rico.ALINHAMENTO_CENTRO)
        volta = rico.aplicar_alinhamento(centro, 0, 2, rico.ALINHAMENTO_ESQUERDA)
        self.assertEqual(volta.corridas[0].atributos.alinhamento, "esquerda")
        self.assertNotEqual(volta.corridas[0].atributos.alinhamento, doc.corridas[0].atributos.alinhamento)


class ValorEmTodoTests(unittest.TestCase):
    """O que a barra pergunta para dizer o estado sob o cursor (S-292)."""

    def test_o_valor_comum_e_devolvido(self) -> None:
        doc = _doc(_texto("um ", alinhamento="centro"), _texto("paragrafo", alinhamento="centro"))
        self.assertEqual(rico.valor_em_todo(doc, 0, len(doc.para_texto()), "alinhamento"), "centro")

    def test_o_valor_divergente_devolve_none(self) -> None:
        """**A distinção que o item existe para manter.** `None` e `""` não são a mesma resposta: a
        lista da barra não pode marcar "centro" onde ele vale em metade da selecao."""
        doc = _doc(_texto("um ", alinhamento="centro"), _texto("outro", alinhamento="direita"))
        self.assertIsNone(rico.valor_em_todo(doc, 0, len(doc.para_texto()), "alinhamento"))

    def test_sem_alinhamento_devolve_a_string_vazia_e_nao_none(self) -> None:
        doc = _doc(_texto("um paragrafo comum"))
        self.assertEqual(rico.valor_em_todo(doc, 0, 5, "alinhamento"), "")

    def test_intervalo_sem_texto_devolve_none(self) -> None:
        doc = _doc(_marca(bloco=0))
        self.assertIsNone(rico.valor_em_todo(doc, 0, len(doc.para_texto()), "alinhamento"))

    def test_o_corpo_tambem_responde(self) -> None:
        doc = _doc(_texto("maior", corpo=2))
        self.assertEqual(rico.valor_em_todo(doc, 0, 5, "corpo"), 2)


class CorpoTests(unittest.TestCase):
    """S-260. O degrau soma sobre o que está lá, e para no limite sem parar o gesto."""

    def test_aumentar_sobe_um_degrau(self) -> None:
        doc = _doc(_texto("uma palavra"))
        maior = rico.mudar_corpo(doc, 0, 3, +1)
        self.assertEqual(maior.corridas[0].atributos.corpo, 1)

    def test_o_degrau_soma_por_corrida_e_nao_achata(self) -> None:
        """**A diferença entre somar e atribuir**, e ela aparece na primeira seleção mista."""
        doc = _doc(_texto("titulo ", corpo=2), _texto("prosa"))
        maior = rico.mudar_corpo(doc, 0, len(doc.para_texto()), +1)
        self.assertEqual([c.atributos.corpo for c in maior.corridas], [3, 1])

    def test_o_limite_para_uma_corrida_e_deixa_a_outra_andar(self) -> None:
        doc = _doc(_texto("no teto ", corpo=rico.CORPO_MAXIMO), _texto("no meio"))
        maior = rico.mudar_corpo(doc, 0, len(doc.para_texto()), +1)
        self.assertEqual(
            [c.atributos.corpo for c in maior.corridas], [rico.CORPO_MAXIMO, 1]
        )

    def test_voltar_ao_normal_zera_o_degrau(self) -> None:
        doc = _doc(_texto("grande demais", corpo=4))
        normal = rico.aplicar_corpo(doc, 0, len(doc.para_texto()), 0)
        self.assertEqual(normal.corridas[0].atributos.corpo, 0)

    def test_passo_zero_nao_mexe_no_documento(self) -> None:
        doc = _doc(_texto("uma palavra"))
        self.assertEqual(rico.mudar_corpo(doc, 0, 3, 0), doc)

    def test_a_marca_do_diagrama_nao_muda_de_corpo(self) -> None:
        doc = _doc(_marca(bloco=0))
        maior = rico.mudar_corpo(doc, 0, len(doc.para_texto()), +1)
        self.assertEqual(maior.corridas[0].atributos.corpo, 0)


class TachadoTests(unittest.TestCase):
    """S-261. É o quarto pincel de ênfase, e ele alterna como os três."""

    def test_o_tachado_e_alternavel(self) -> None:
        """Derivado de `fields(Atributos)`: entrar em `BOOLEANOS` não custou uma linha."""
        self.assertIn("tachado", rico.BOOLEANOS)

    def test_alternar_liga_e_desliga(self) -> None:
        doc = _doc(_texto("uma palavra"))
        riscado = rico.alternar(doc, 0, 3, "tachado")
        self.assertTrue(riscado.corridas[0].atributos.tachado)
        self.assertFalse(rico.alternar(riscado, 0, 3, "tachado").corridas[0].atributos.tachado)

    def test_selecionar_meio_riscado_completa_o_risco(self) -> None:
        """A pergunta é "vale em **todo** o intervalo?", como no negrito da S-241."""
        doc = _doc(_texto("ja risca", tachado=True), _texto("do e este"))
        inteiro = rico.alternar(doc, 0, len(doc.para_texto()), "tachado")
        self.assertTrue(all(c.atributos.tachado for c in inteiro.corridas))

    def test_limpar_formato_nao_leva_o_alinhamento_nem_o_corpo(self) -> None:
        """Os dois têm comando próprio de volta ao normal -- ver `texto_panel.ATRIBUTOS_DE_ENFASE`."""
        doc = _doc(_texto("um trecho", negrito=True, alinhamento="centro", corpo=2))
        limpo = rico.limpar_formato(doc, 0, len(doc.para_texto()))
        self.assertFalse(limpo.corridas[0].atributos.negrito)
        self.assertEqual(limpo.corridas[0].atributos.alinhamento, "centro")
        self.assertEqual(limpo.corridas[0].atributos.corpo, 2)


class CaixaTests(unittest.TestCase):
    """S-262. Muda o texto, e por isso o que ela **não** toca é metade do item."""

    def test_maiuscula_e_minuscula(self) -> None:
        doc = _doc(_texto("Uma Frase Assim"))
        alto = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_ALTA)
        baixo = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_BAIXA)
        self.assertEqual(alto.para_texto(), "UMA FRASE ASSIM")
        self.assertEqual(baixo.para_texto(), "uma frase assim")

    def test_iniciais_partem_no_hifen_e_nao_no_apostrofo(self) -> None:
        """**As duas regras do Title Case, e as duas são medidas no acervo** (S-262).

        `str.title()` acerta o hífen e erra o apóstrofo: ela devolve `Don'T`. Uma regra que
        reusasse `palavra_em` acertaria o apóstrofo e erraria o hífen -- `Saint-amant` num índice de
        nomes de jogador. Ver `rico.NAO_ABREM_PALAVRA`."""
        doc = _doc(_texto("d'angelo e saint-amant não param"))
        iniciais = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_INICIAIS)
        self.assertEqual(iniciais.para_texto(), "D'angelo E Saint-Amant Não Param")
        self.assertEqual("d'angelo e saint-amant não param".title(), "D'Angelo E Saint-Amant Não Param")

    def test_a_caixa_preserva_os_atributos_de_cada_corrida(self) -> None:
        """**Corrida a corrida**: passar o intervalo inteiro por `substituir_intervalo` daria o
        negrito da primeira corrida em todas."""
        doc = _doc(_texto("negrito ", negrito=True), _texto("comum"))
        alto = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_ALTA)
        self.assertEqual([c.atributos.negrito for c in alto.corridas], [True, False])
        self.assertEqual(alto.para_texto(), "NEGRITO COMUM")

    def test_a_marca_do_diagrama_atravessa_intacta(self) -> None:
        """O que se perderia não é a caixa: é o vínculo entre o texto e a figura."""
        doc = _doc(_texto("antes ", bloco=0), _marca(3, bloco=0))
        alto = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_ALTA)
        self.assertEqual(alto.para_texto(), "ANTES [Diagrama 3]")

    def test_a_caixa_carimba_humano_so_no_que_mudou(self) -> None:
        """Trecho que já estava na caixa pedida não vira correção -- ele não foi corrigido."""
        doc = _doc(
            rico.Corrida(texto="JA ALTO ", bloco=0, procedencia="glifo"),
            rico.Corrida(texto="baixo", bloco=0, procedencia="glifo"),
        )
        alto = rico.mudar_caixa(doc, 0, len(doc.para_texto()), rico.CAIXA_ALTA)
        self.assertEqual([c.procedencia for c in alto.corridas], ["glifo", "humano"])

    def test_sem_selecao_o_alvo_e_a_palavra(self) -> None:
        """A regra de `intervalo_alvo`, que vale para toda ferramenta desde a S-241."""
        doc = _doc(_texto("uma palavra inteira"))
        alto = rico.mudar_caixa(doc, 5, 5, rico.CAIXA_ALTA)
        self.assertEqual(alto.para_texto(), "uma PALAVRA inteira")

    def test_a_faixa_de_confianca_sobrevive_a_troca(self) -> None:
        """Trocar a caixa não é dizer que o motor acertou: a régua é de outro dono."""
        doc = _doc(rico.Corrida(texto="duvidoso", faixa=documento.REVISAR, bloco=0))
        alto = rico.mudar_caixa(doc, 0, 8, rico.CAIXA_ALTA)
        self.assertEqual(alto.corridas[0].faixa, documento.REVISAR)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
