"""A fila de revisão de caractere, ordenada por valor de informação (S-212).

**Os três critérios de aceite do item viram três testes com o nome que a spec deu**, e o terceiro
é o mais importante: a cor do box e a posição na fila concordam. No projeto de origem elas
discordaram, e um box verde no topo da fila destrói a confiança na fila inteira -- aqui a garantia
é estrutural (uma função só decide as duas), e o teste afirma a consequência.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from chess_diagram_ocr.text import documento
from chess_diagram_ocr.text.fila import (
    CAMINHO_PADRAO,
    VERSAO,
    Fila,
    FilaInvalida,
    Item,
    de_lidos,
    de_pagina,
    ordenar,
)
from chess_diagram_ocr.text.leitura_de_linha import Lido


def item(texto: str = "a", confianca: float = 0.5, **campos: object) -> Item:
    base = {"documento": "livro.pdf", "pagina": 0, "coluna": 0, "linha": 0}
    base.update(campos)
    return Item(texto=texto, confianca=confianca, **base)  # type: ignore[arg-type]


class OrdenacaoTests(unittest.TestCase):
    def test_a_fila_ordena_por_divergencia(self) -> None:
        """A régua da S-189: divergir dá `min`, e o `min` põe o box na frente.

        O par tem a **mesma** leitura do glifo com a mesma confiança bruta; o que os separa é o
        segundo leitor ter concordado ou não -- que é exatamente o que a S-189 mede.
        """
        concorda = de_lidos([Lido("c", 0.90, "c", "c")], faixas=documento.FAIXAS)[0]
        diverge = de_lidos([Lido("c", 0.40, "c", "e")], faixas=documento.FAIXAS)[0]
        fila = ordenar([concorda, diverge])
        self.assertTrue(fila[0].divergem, "o item divergente não veio primeiro")
        self.assertEqual("e", fila[0].do_bloco)

    def test_o_de_menor_confianca_vem_primeiro(self) -> None:
        fila = ordenar([item("a", 0.9), item("b", 0.1, linha=1), item("c", 0.5, linha=2)])
        self.assertEqual(["b", "c", "a"], [i.texto for i in fila])

    def test_a_ordem_e_a_mesma_entre_duas_execucoes(self) -> None:
        """Sem desempate estável, "o terceiro item" não quer dizer nada de uma sessão para outra."""
        empatados = [item("z", 0.5, linha=2), item("a", 0.5, linha=0), item("m", 0.5, linha=1)]
        self.assertEqual(
            [i.chave for i in ordenar(empatados)],
            [i.chave for i in ordenar(list(reversed(empatados)))],
        )

    def test_a_margem_nao_entra_na_ordenacao(self) -> None:
        """A spec é explícita: só com tabela ao lado, e a tabela não foi medida aqui."""
        alta = item("a", 0.5, margem=0.99)
        baixa = item("b", 0.4, margem=0.01, linha=1)
        self.assertEqual(["b", "a"], [i.texto for i in ordenar([alta, baixa])])

    def test_a_fila_vazia_ordena_sem_estourar(self) -> None:
        self.assertEqual([], ordenar([]))


class CorETests(unittest.TestCase):
    def test_a_cor_do_box_e_a_posicao_na_fila_concordam(self) -> None:
        """Nunca um box mais verde na frente de um mais vermelho. Ver o cabeçalho do módulo."""
        ordem = {"revisar": 0, "conferir": 1, "tranquilo": 2}
        confiancas = [0.05, 0.2, 0.4, 0.6, 0.74, 0.76, 0.9, 0.999]
        fila = ordenar([item("x", c, linha=n) for n, c in enumerate(confiancas)])
        faixas = [ordem[i.faixa] for i in fila]
        self.assertEqual(sorted(faixas), faixas, f"faixa fora de ordem na fila: {faixas}")

    def test_a_faixa_do_item_e_a_do_editor(self) -> None:
        """Uma função só decide as duas coisas -- não dois números que podem divergir."""
        for confianca in (0.0, 0.29, 0.31, 0.74, 0.76, 1.0):
            with self.subTest(confianca=confianca):
                self.assertEqual(documento.faixa_de_confianca(confianca), item("a", confianca).faixa)

    def test_a_camada_de_texto_nunca_pede_revisao(self) -> None:
        """A regra vem de `faixa_de_confianca`, e a fila a herda por usar a mesma função."""
        self.assertEqual("tranquilo", item("a", 0.0, procedencia="camada").faixa)

    def test_a_distribuicao_conta_por_faixa(self) -> None:
        """É a resposta ao CORTE_DE_CONFERIR de 0,75, que foi declarado esperando esta S-212."""
        fila = Fila(tuple(item("x", c, linha=n) for n, c in enumerate((0.1, 0.5, 0.9, 0.95))))
        self.assertEqual({"revisar": 1, "conferir": 1, "tranquilo": 2}, fila.distribuicao())


class PersistenciaTests(unittest.TestCase):
    """Lá, salvar zerava a fila, e o defeito ficou documentado como desenho por meses."""

    def fila(self) -> Fila:
        crus = [item("a", 0.1), item("b", 0.5, linha=1), item("c", 0.7, linha=2)]
        return Fila(tuple(ordenar(crus)))

    def test_salvar_e_reabrir_preserva_a_fila(self) -> None:
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "fila.json"
            antes = self.fila().marcar(("livro.pdf", 0, 0, 1, -1), "revisado", corrigido="B")
            antes.salvar(destino)
            depois = Fila.abrir(destino)

        self.assertEqual(len(antes), len(depois))
        self.assertEqual([i.chave for i in antes], [i.chave for i in depois])
        revisado = next(i for i in depois if i.linha == 1)
        self.assertEqual("revisado", revisado.estado)
        self.assertEqual("B", revisado.corrigido)

    def test_reabrir_nao_reordena_o_que_ja_foi_revisado(self) -> None:
        """Se `de_json` reordenasse, o item marcado voltaria para perto do topo."""
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "fila.json"
            antes = self.fila().marcar(("livro.pdf", 0, 0, 0, -1), "revisado")
            antes.salvar(destino)
            self.assertEqual([i.chave for i in antes], [i.chave for i in Fila.abrir(destino)])

    def test_o_revisado_sai_dos_pendentes_e_fica_na_fila(self) -> None:
        marcada = self.fila().marcar(("livro.pdf", 0, 0, 0, -1), "revisado")
        self.assertEqual(3, len(marcada))
        self.assertEqual(2, len(marcada.pendentes))

    def test_marcar_devolve_fila_nova_e_nao_mexe_na_ordem(self) -> None:
        original = self.fila()
        marcada = original.marcar(("livro.pdf", 0, 0, 2, -1), "descartado")
        self.assertIsNot(original, marcada)
        self.assertEqual("pendente", original.itens[-1].estado)
        self.assertEqual([i.chave for i in original], [i.chave for i in marcada])

    def test_marcar_chave_desconhecida_devolve_a_mesma_fila(self) -> None:
        original = self.fila()
        self.assertIs(original, original.marcar(("outro.pdf", 9, 9, 9, 9), "revisado"))

    def test_arquivo_ausente_abre_fila_vazia(self) -> None:
        with TemporaryDirectory() as pasta:
            self.assertEqual(0, len(Fila.abrir(Path(pasta) / "nao_existe.json")))

    def test_arquivo_estragado_levanta_em_vez_de_apagar(self) -> None:
        """Uma fila vazia por cima de um arquivo ilegível apagaria a tarde de quem revisou."""
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "fila.json"
            destino.write_text(json.dumps({"versao": VERSAO, "itens": "nao é lista"}), encoding="utf-8")
            with self.assertRaises(FilaInvalida):
                Fila.abrir(destino)

    def test_versao_do_futuro_e_recusada(self) -> None:
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "fila.json"
            destino.write_text(json.dumps({"versao": VERSAO + 1, "itens": []}), encoding="utf-8")
            with self.assertRaises(FilaInvalida):
                Fila.abrir(destino)

    def test_estado_desconhecido_no_arquivo_vira_pendente(self) -> None:
        """Nunca sumir com o item: um estado que esta build não conhece pede olho, não silêncio."""
        lido = Item.de_json({"documento": "l.pdf", "texto": "a", "confianca": 0.1, "estado": "inventado"})
        self.assertEqual("pendente", lido.estado)

    def test_o_caminho_padrao_fica_em_data(self) -> None:
        self.assertEqual("data", CAMINHO_PADRAO.parent.name)


class ReguaTests(unittest.TestCase):
    def test_sem_leitor_de_linha_a_regua_e_a_confianca(self) -> None:
        """`modo_bloco` está desligado por padrão desde a S-188: é o estado normal do programa."""
        so_glifo = de_lidos([Lido("a", 0.2, "a", "")], faixas=documento.FAIXAS)
        self.assertEqual("confianca", Fila(tuple(so_glifo)).regua)

    def test_com_leitor_de_linha_a_regua_e_a_divergencia(self) -> None:
        com_bloco = de_lidos([Lido("a", 0.2, "a", "a")], faixas=documento.FAIXAS)
        self.assertEqual("divergencia", Fila(tuple(com_bloco)).regua)

    def test_a_regua_viaja_no_json(self) -> None:
        """Uma fila que não diz por que ordenou assim é uma lista."""
        self.assertIn("regua", Fila(()).para_json())


class AdmissaoTests(unittest.TestCase):
    def test_o_tranquilo_fica_de_fora(self) -> None:
        """Pôr as ~2.000 leituras da página numa lista seria a página outra vez."""
        self.assertEqual([], de_lidos([Lido("a", 0.99, "a", "a")]))

    def test_o_divergente_entra_mesmo_verde(self) -> None:
        """Duas leituras confiantes que discordam é a informação mais forte da página."""
        entrou = de_lidos([Lido("c", 0.90, "c", "e")])
        self.assertEqual(1, len(entrou))
        self.assertEqual("tranquilo", entrou[0].faixa)

    def test_o_divergente_verde_entra_no_fim_e_nao_no_topo(self) -> None:
        """O critério de aceite proíbe verde no **topo**, e é isto que garante que não vai."""
        fila = de_lidos([Lido("c", 0.90, "c", "e"), Lido("a", 0.10, "a", "a")])
        self.assertEqual("a", fila[0].texto)
        self.assertEqual("c", fila[-1].texto)

    def test_de_lidos_marca_o_box_e_de_pagina_marca_menos_um(self) -> None:
        """O `box` é o que diz se o item é de caractere ou de linha. Ver `de_pagina`."""
        self.assertEqual(0, de_lidos([Lido("a", 0.1, "a", "a")])[0].box)


class DePaginaTests(unittest.TestCase):
    def pagina(self):
        from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

        linhas = tuple(
            LinhaLida(texto=t, bbox=(0, n * 10, 100, n * 10 + 9), confianca=c, procedencia="glifo")
            for n, (t, c) in enumerate((("boa", 0.99), ("ruim", 0.10), ("media", 0.60)))
        )
        bloco = BlocoDeTexto(linhas=linhas, bbox=(0, 0, 100, 30), confianca=0.10, procedencia="glifo")
        return PaginaLida(
            documento="livro.pdf",
            pagina=7,
            largura=100.0,
            altura=100.0,
            colunas=(Coluna(indice=0, blocos=(bloco,), bbox=(0, 0, 100, 30)),),
        )

    def test_de_pagina_traz_so_o_que_pede_olho_e_ja_ordenado(self) -> None:
        itens = de_pagina(self.pagina())
        self.assertEqual(["ruim", "media"], [i.texto for i in itens])
        self.assertEqual(7, itens[0].pagina)
        self.assertEqual("livro.pdf", itens[0].documento)

    def test_de_pagina_marca_box_menos_um(self) -> None:
        """A `PaginaLida` guarda linha, e não box: dizer `box=0` seria mentir sobre a granularidade."""
        self.assertTrue(all(i.box == -1 for i in de_pagina(self.pagina())))

    def test_de_pagina_com_todas_as_faixas_traz_a_pagina_inteira(self) -> None:
        self.assertEqual(3, len(de_pagina(self.pagina(), faixas=documento.FAIXAS)))

    def test_de_pagina_guarda_a_bbox_da_linha(self) -> None:
        primeiro = de_pagina(self.pagina())[0]
        self.assertEqual((0.0, 10.0, 100.0, 19.0), primeiro.bbox)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
