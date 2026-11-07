"""O ouro da régua da prosa (S-702): o sorteio é fixo, e o manifesto não aceita o que o invalidaria.

As três guardas que a S-702 pede são as de `ManifestoTests`: folha sem identidade, livro em dois
splits, e teste lido antes de o manifesto ser congelado. `VersionadoTests` confere o manifesto que o
repositório guarda -- é ele que os portões G102 a G107 abrem.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from chess_diagram_ocr.text import ouro

L = ouro.LivroDoOuro
F = ouro.FolhaDoOuro


def _id(n: int) -> str:
    return f"{n:016x}"


def _manifesto(livros: list[ouro.LivroDoOuro], folhas: list[ouro.FolhaDoOuro], **kw: object) -> ouro.Manifesto:
    base = {"versao": ouro.VERSAO, "congelado_em": "2026-10-30", "primeira_leitura_do_teste": None}
    base.update(kw)
    return ouro.Manifesto(livros=tuple(livros), folhas=tuple(folhas), **base)  # type: ignore[arg-type]


def _sem_espanhol(m: ouro.Manifesto, **kw: object) -> ouro.Manifesto:
    """O mesmo teste com o livro em espanhol passado a inglês -- o livro e as folhas dele."""
    def ingles(lingua: str) -> str:
        return "eng" if lingua == "spa" else lingua

    livros = [L(x.identidade, x.split, ingles(x.lingua)) for x in m.livros]
    folhas = [F(f.identidade, f.folha, ingles(f.lingua), f.estrato, f.split) for f in m.folhas]
    return _manifesto(livros, folhas, **kw)


def _teste_valido() -> ouro.Manifesto:
    linguas = ["eng"] * 10 + ["por", "spa"]
    livros = [L(_id(i), ouro.TESTE, lingua) for i, lingua in enumerate(linguas)]
    folhas = [F(livro.identidade, 10 + k, livro.lingua, ouro.PROSA, ouro.TESTE) for livro in livros for k in range(6)]
    livros.append(L(_id(99), ouro.DEV, "eng"))
    folhas.append(F(_id(99), 155, "eng", ouro.PROSA, ouro.DEV))
    return _manifesto(livros, folhas)


class OrdemTests(unittest.TestCase):
    def test_valores_conhecidos(self) -> None:
        """A regra escrita, conferida por fora: sha256(identidade + folha) e sha256("semente:" + identidade)."""
        self.assertEqual([50, 29, 68, 32, 33, 15], ouro.ordem_das_folhas(_id(7), 100)[:6])
        self.assertEqual([_id(5), _id(3), _id(2)], ouro.ordem_dos_livros([_id(i) for i in range(6)], "20261030")[:3])

    def test_folhas_em_base_1_sem_as_pontas_e_fixas(self) -> None:
        ordem = ouro.ordem_das_folhas(_id(7), 100)
        self.assertEqual(list(range(9, 93)), sorted(ordem))
        self.assertEqual(ordem, ouro.ordem_das_folhas(_id(7), 100))
        self.assertNotEqual(ordem, ouro.ordem_das_folhas(_id(8), 100))

    def test_ordem_dos_livros_nao_depende_da_lista(self) -> None:
        ids = [_id(i) for i in range(20)]
        self.assertEqual(ouro.ordem_dos_livros(ids, "s"), ouro.ordem_dos_livros(reversed(ids), "s"))
        self.assertNotEqual(ouro.ordem_dos_livros(ids, "s"), ouro.ordem_dos_livros(ids, "t"))


def _classe(token: str) -> str:
    return "notacao" if token[:1].isdigit() else "prosa"


def _texto(prosa: int, notacao: int) -> str:
    """Tokens de 10 caracteres: `prosa` de letras e `notacao` que começam por dígito."""
    return " ".join(["abcdefghij"] * prosa + ["1234567890"] * notacao)


class EstratoTests(unittest.TestCase):
    def test_os_limites_sao_os_do_dev(self) -> None:
        self.assertEqual((700, 0.55, 1.01), ouro.ESTRATO_PROSA)
        self.assertEqual((300, 0.20, 0.55), ouro.ESTRATO_MISTO)
        self.assertEqual(0.08, ouro.PULAR)

    def test_fronteiras(self) -> None:
        self.assertEqual(ouro.PROSA, ouro.estrato_do_texto(_texto(70, 0), _classe))  # 700 de prosa
        self.assertIsNone(ouro.estrato_do_texto(_texto(69, 0) + " abcdefghi", _classe))  # 699
        self.assertEqual(ouro.PROSA, ouro.estrato_do_texto(_texto(77, 63), _classe))  # 55% exatos
        self.assertEqual(ouro.MISTO, ouro.estrato_do_texto(_texto(77, 64), _classe))  # 54,6%
        self.assertEqual(ouro.MISTO, ouro.estrato_do_texto(_texto(40, 160), _classe))  # 20% exatos
        self.assertIsNone(ouro.estrato_do_texto(_texto(40, 161), _classe))  # 19,9%
        self.assertEqual(ouro.MISTO, ouro.estrato_do_texto(_texto(30, 30), _classe))  # 300 de prosa
        self.assertIsNone(ouro.estrato_do_texto(_texto(29, 30), _classe))  # 290

    def test_prosa_misto_e_nada(self) -> None:
        self.assertEqual(ouro.PROSA, ouro.estrato_do_texto("palavra " * 120, _classe))
        self.assertEqual(ouro.MISTO, ouro.estrato_do_texto("palavra " * 60 + "12.Nf3 " * 120, _classe))
        self.assertIsNone(ouro.estrato_do_texto("12.Nf3 " * 200, _classe))
        self.assertIsNone(ouro.estrato_do_texto("curta", _classe))


class SortearFolhasTests(unittest.TestCase):
    def test_tres_de_cada_estrato_e_admissao_so_quando_precisa(self) -> None:
        perguntadas: list[int] = []

        def admitida(folha: int) -> bool:
            perguntadas.append(folha)
            return folha % 7 != 0

        escolhidas = ouro.sortear_folhas(_id(1), 300, lambda f: ouro.PROSA if f % 2 else ouro.MISTO, admitida)
        self.assertEqual(3, sum(e == ouro.PROSA for _, e in escolhidas))
        self.assertEqual(3, sum(e == ouro.MISTO for _, e in escolhidas))
        self.assertTrue(all(f % 7 for f, _ in escolhidas))
        self.assertLessEqual(len(perguntadas), 6 + sum(1 for f in perguntadas if f % 7 == 0))

    def test_estrato_que_falta_e_completado_pelo_outro(self) -> None:
        escolhidas = ouro.sortear_folhas(_id(2), 300, lambda f: ouro.PROSA, lambda f: True)
        self.assertEqual(6, len(escolhidas))
        self.assertTrue(all(e == ouro.PROSA for _, e in escolhidas))

    def test_mesmo_sorteio_duas_vezes(self) -> None:
        def estrato(f: int) -> str | None:
            return (ouro.PROSA, ouro.MISTO, None)[f % 3]

        a = ouro.sortear_folhas(_id(3), 500, estrato, lambda f: True)
        self.assertEqual(a, ouro.sortear_folhas(_id(3), 500, estrato, lambda f: True))


class SortearLivrosTests(unittest.TestCase):
    def _candidatos(self) -> list[ouro.LivroDoOuro]:
        eng = [L(_id(i), ouro.RESERVA, "eng", "ebook" if i % 3 else "pdf") for i in range(30)]
        return [*eng, L(_id(100), ouro.RESERVA, "por", "pdf"), L(_id(101), ouro.RESERVA, "spa", "ebook")]

    def test_linguas_inteiras_entram_e_o_total_fecha(self) -> None:
        escolhidos = ouro.sortear_livros(self._candidatos(), 16, "20261030", linguas_inteiras={"por", "spa"})
        self.assertEqual(16, len(escolhidos))
        self.assertIn(_id(100), escolhidos)
        self.assertIn(_id(101), escolhidos)

    def test_origens_na_proporcao(self) -> None:
        candidatos = self._candidatos()
        escolhidos = set(ouro.sortear_livros(candidatos, 16, "20261030", linguas_inteiras={"por", "spa"}))
        origem = {c.identidade: c.origem for c in candidatos if c.lingua == "eng"}
        pdf = sum(origem.get(i) == "pdf" for i in escolhidos)
        self.assertEqual(5, pdf)  # 10 de 30 em inglês são pdf: 14 vagas x 1/3 = 4,67 -> 5

    def test_nao_depende_da_ordem_dos_candidatos(self) -> None:
        c = self._candidatos()
        self.assertEqual(
            ouro.sortear_livros(c, 16, "s", linguas_inteiras={"por"}),
            ouro.sortear_livros(list(reversed(c)), 16, "s", linguas_inteiras={"por"}),
        )


class ManifestoTests(unittest.TestCase):
    def test_manifesto_valido_nao_tem_problema(self) -> None:
        self.assertEqual([], ouro.problemas(_teste_valido()))

    def test_folha_sem_identidade_reprova(self) -> None:
        m = _teste_valido()
        m = _manifesto(list(m.livros), [*m.folhas, F("", 3, "eng", ouro.PROSA, ouro.TESTE)])
        self.assertTrue(any("sem identidade" in p for p in ouro.problemas(m)))

    def test_livro_nos_dois_splits_reprova(self) -> None:
        m = _teste_valido()
        m = _manifesto([*m.livros, L(_id(0), ouro.DEV, "eng")], list(m.folhas))
        self.assertTrue(any("dois splits" in p for p in ouro.problemas(m)))

    def test_teste_lido_antes_de_congelado_reprova(self) -> None:
        m = _teste_valido()
        cedo = _manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="2026-10-29")
        depois = _manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="2026-11-02")
        self.assertTrue(any("antes de o manifesto" in p for p in ouro.problemas(cedo)))
        self.assertEqual([], ouro.problemas(depois))

    def test_folha_no_split_errado_ou_de_livro_desconhecido_reprova(self) -> None:
        m = _teste_valido()
        errada = _manifesto(list(m.livros), [*m.folhas, F(_id(99), 200, "eng", ouro.PROSA, ouro.TESTE)])
        orfa = _manifesto(list(m.livros), [*m.folhas, F(_id(55), 200, "eng", ouro.PROSA, ouro.TESTE)])
        self.assertTrue(any("e o livro não" in p for p in ouro.problemas(errada)))
        self.assertTrue(any("não lista" in p for p in ouro.problemas(orfa)))

    def test_teste_pequeno_ou_de_poucas_linguas_reprova(self) -> None:
        m = _teste_valido()
        so_ingles = [L(x.identidade, x.split, "eng") for x in m.livros]
        folhas = [F(f.identidade, f.folha, "eng", f.estrato, f.split) for f in m.folhas]
        self.assertTrue(any("línguas" in p for p in ouro.problemas(_manifesto(so_ingles, folhas))))
        poucos = [x for x in m.livros if x.split != ouro.TESTE][:1] + [x for x in m.livros if x.split == ouro.TESTE][:5]
        ids = {x.identidade for x in poucos}
        self.assertTrue(any("mínimo" in p for p in ouro.problemas(_manifesto(poucos, [f for f in m.folhas if f.identidade in ids]))))

    def test_lingua_pendente_so_vale_declarada_e_sai_quando_cumprida(self) -> None:
        m = _teste_valido()
        self.assertTrue(any("línguas" in p for p in ouro.problemas(_sem_espanhol(m))))
        aceita = _sem_espanhol(m, pendencias=(ouro.PENDENCIA_DE_LINGUA,))
        self.assertEqual([], ouro.problemas(aceita))
        esquecida = _manifesto(list(m.livros), list(m.folhas), pendencias=(ouro.PENDENCIA_DE_LINGUA,))
        self.assertTrue(any("não saiu" in p for p in ouro.problemas(esquecida)))
        inventada = _manifesto(list(m.livros), list(m.folhas), pendencias=("qualquer",))
        self.assertTrue(any("sem regra" in p for p in ouro.problemas(inventada)))

    def test_livro_reprovado_so_na_reserva_e_fora_do_treino(self) -> None:
        m = _teste_valido()
        no_teste = [L(x.identidade, x.split, x.lingua, reprovado="auditoria: x") if x.identidade == _id(0) else x
                    for x in m.livros]
        self.assertTrue(any("reprovado" in p for p in ouro.problemas(_manifesto(no_teste, list(m.folhas)))))
        no_treino = L(_id(88), ouro.RESERVA, "eng", reprovado="auditoria: x")
        self.assertTrue(any("reprovado" in p for p in ouro.problemas(_manifesto([*m.livros, no_treino], list(m.folhas)))))
        certo = L(_id(88), ouro.RESERVA, "eng", reprovado="auditoria: x", fora_do_treino=True)
        self.assertEqual([], ouro.problemas(_manifesto([*m.livros, certo], list(m.folhas))))

    def test_irmao_de_serie_de_livro_do_teste_tem_de_estar_fora_do_treino(self) -> None:
        m = _teste_valido()
        irmao = L(_id(77), ouro.RESERVA, "eng", grupo=_id(0))
        self.assertTrue(any("fora_do_treino" in p for p in ouro.problemas(_manifesto([*m.livros, irmao], list(m.folhas)))))
        ok = L(_id(77), ouro.RESERVA, "eng", grupo=_id(0), fora_do_treino=True)
        self.assertEqual([], ouro.problemas(_manifesto([*m.livros, ok], list(m.folhas))))

    def test_gravar_e_carregar_ida_e_volta_em_lf(self) -> None:
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "ouro.json"
            ouro.gravar(_teste_valido(), caminho)
            self.assertNotIn(b"\r", caminho.read_bytes())
            self.assertEqual(_teste_valido(), ouro.carregar(caminho))


class SobrasTests(unittest.TestCase):
    """O estrato que falta se completa com **todas** as folhas do outro (achado B1 do crítico)."""

    def test_as_seis_primeiras_sobras_recusadas_e_a_setima_entra(self) -> None:
        ordem = ouro.ordem_das_folhas(_id(4), 300)
        recusadas = set(ordem[3:9])  # as seis primeiras sobras, depois das três que enchem o misto
        escolhidas = ouro.sortear_folhas(_id(4), 300, lambda f: ouro.MISTO, lambda f: f not in recusadas)
        self.assertEqual(ordem[:3] + ordem[9:12], [f for f, _ in escolhidas])

    def test_todas_as_sobras_menos_as_ultimas_tres_recusadas(self) -> None:
        """O livro do achado precisou de 17 sobras; aqui são 246 recusadas antes das três que entram."""
        ordem = ouro.ordem_das_folhas(_id(6), 300)
        aceitas = set(ordem[:3]) | set(ordem[-3:])
        escolhidas = ouro.sortear_folhas(_id(6), 300, lambda f: ouro.MISTO, lambda f: f in aceitas)
        self.assertEqual(ordem[:3] + ordem[-3:], [f for f, _ in escolhidas])

    def test_o_completamento_pergunta_a_admissao(self) -> None:
        ordem = ouro.ordem_das_folhas(_id(5), 300)
        recusadas = set(ordem[3::2])  # metade das sobras recusada
        escolhidas = [f for f, _ in ouro.sortear_folhas(_id(5), 300, lambda f: ouro.PROSA, lambda f: f not in recusadas)]
        self.assertEqual(6, len(escolhidas))
        self.assertFalse(recusadas & set(escolhidas))


DIA = "2026-11-05"


class AcrescentarTests(unittest.TestCase):
    """O livro da terceira língua entra a mais, sem mexer em nada sorteado (achado I2 do crítico)."""

    def _duas_linguas(self) -> ouro.Manifesto:
        return _sem_espanhol(_teste_valido(), pendencias=(ouro.PENDENCIA_DE_LINGUA,))

    def _seis(self) -> list[tuple[int, str]]:
        return [(10 + k, ouro.PROSA) for k in range(6)]

    def test_entra_a_mais_e_a_pendencia_sai(self) -> None:
        m = self._duas_linguas()
        novo = ouro.acrescentar_ao_teste(m, L(_id(200), ouro.RESERVA, "deu", "pdf"), self._seis(), entrou_em=DIA)
        self.assertEqual(m.livros, novo.livros[: len(m.livros)])
        self.assertEqual(m.folhas, novo.folhas[: len(m.folhas)])
        self.assertEqual((), novo.pendencias)
        self.assertEqual(ouro.TESTE, novo.livros[-1].split)
        self.assertEqual(DIA, novo.livros[-1].entrou_em)
        self.assertEqual([], ouro.problemas(novo))

    def test_entrar_no_dia_do_congelamento_e_ir_e_voltar_pelo_arquivo(self) -> None:
        novo = ouro.acrescentar_ao_teste(self._duas_linguas(), L(_id(223), ouro.RESERVA, "deu"), self._seis(),
                                         entrou_em="2026-10-30")
        self.assertEqual("2026-10-30", novo.livros[-1].entrou_em)
        with TemporaryDirectory() as tmp:
            ouro.gravar(novo, Path(tmp) / "ouro.json")
            self.assertEqual(novo, ouro.carregar(Path(tmp) / "ouro.json"))

    def test_a_data_de_entrada_e_de_depois_do_congelamento(self) -> None:
        for data in ("2026-10-29", "05/11/2026", "2026-11-05x"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                ouro.acrescentar_ao_teste(self._duas_linguas(), L(_id(220), ouro.RESERVA, "deu"), self._seis(),
                                          entrou_em=data)

    def test_a_lingua_da_reserva_nao_conta(self) -> None:
        """Só as línguas do **teste** tiram a pendência: um livro em espanhol na reserva não."""
        m = self._duas_linguas()
        m = _manifesto([*m.livros, L(_id(221), ouro.RESERVA, "spa")], list(m.folhas), pendencias=m.pendencias)
        novo = ouro.acrescentar_ao_teste(m, L(_id(222), ouro.RESERVA, "eng"), self._seis(), entrou_em=DIA)
        self.assertEqual((ouro.PENDENCIA_DE_LINGUA,), novo.pendencias)

    def test_a_serie_toda_sai_do_treino(self) -> None:
        """O representante e os dois irmãos: os irmãos apontam o representante pelo `grupo`."""
        m = self._duas_linguas()
        rep, a, b = L(_id(230), ouro.RESERVA, "eng"), L(_id(231), ouro.RESERVA, "eng", grupo=_id(230)), \
            L(_id(232), ouro.RESERVA, "eng", grupo=_id(230))
        m = _manifesto([*m.livros, rep, a, b], list(m.folhas), pendencias=m.pendencias)
        novo = ouro.acrescentar_ao_teste(m, L(_id(233), ouro.RESERVA, "deu", grupo=_id(230)), self._seis(), entrou_em=DIA)
        por_id = {x.identidade: x for x in novo.livros}
        self.assertTrue(all(por_id[i].fora_do_treino for i in (_id(230), _id(231), _id(232))))
        self.assertEqual([], ouro.problemas(novo))

    def test_a_serie_do_teste_se_reconhece_pelo_grupo(self) -> None:
        """O livro do teste que é membro (não representante) de uma série barra o irmão que chega."""
        m = self._duas_linguas()
        livros = [L(x.identidade, x.split, x.lingua, grupo=_id(240)) if x.identidade == _id(0) else x for x in m.livros]
        m = _manifesto([*livros, L(_id(240), ouro.RESERVA, "eng", fora_do_treino=True)], list(m.folhas),
                       pendencias=m.pendencias)
        self.assertEqual([], ouro.problemas(m))
        with self.assertRaises(ValueError):
            ouro.acrescentar_ao_teste(m, L(_id(241), ouro.RESERVA, "deu", grupo=_id(240)), self._seis(), entrou_em=DIA)

    def test_outra_lingua_ja_vista_nao_tira_a_pendencia(self) -> None:
        m = self._duas_linguas()
        novo = ouro.acrescentar_ao_teste(m, L(_id(201), ouro.RESERVA, "eng", "pdf"), self._seis(), entrou_em=DIA)
        self.assertEqual((ouro.PENDENCIA_DE_LINGUA,), novo.pendencias)

    def test_diagramacao_vista_e_poucas_folhas_nao_entram(self) -> None:
        m = self._duas_linguas()
        with self.assertRaises(ValueError):
            ouro.acrescentar_ao_teste(m, L(_id(202), ouro.RESERVA, "deu", diagramacao="vista"), self._seis(), entrou_em=DIA)
        with self.assertRaises(ValueError):
            ouro.acrescentar_ao_teste(m, L(_id(203), ouro.RESERVA, "deu"), self._seis()[:5], entrou_em=DIA)

    def test_serie_que_ja_tem_livro_no_teste_nao_ganha_outro(self) -> None:
        with self.assertRaises(ValueError):
            ouro.acrescentar_ao_teste(self._duas_linguas(), L(_id(204), ouro.RESERVA, "deu", grupo=_id(0)), self._seis(), entrou_em=DIA)

    def test_os_irmaos_de_serie_na_reserva_saem_do_treino(self) -> None:
        m = self._duas_linguas()
        irmao = L(_id(205), ouro.RESERVA, "deu")
        m = _manifesto([*m.livros, irmao], list(m.folhas), pendencias=m.pendencias)
        novo = ouro.acrescentar_ao_teste(m, L(_id(206), ouro.RESERVA, "deu", grupo=_id(205)), self._seis(), entrou_em=DIA)
        self.assertTrue(next(x for x in novo.livros if x.identidade == _id(205)).fora_do_treino)
        self.assertEqual([], ouro.problemas(novo))

    def test_livro_que_ja_esta_no_manifesto_nao_entra(self) -> None:
        with self.assertRaises(ValueError):
            ouro.acrescentar_ao_teste(_teste_valido(), L(_id(99), ouro.DEV, "eng"), self._seis(), entrou_em=DIA)


class CadaGuardaTests(unittest.TestCase):
    """Cada guarda de `problemas` dispara sozinha, num manifesto que fora dela vale (achado I1)."""

    def _so(self, m: ouro.Manifesto, trecho: str) -> None:
        erros = ouro.problemas(m)
        self.assertEqual(1, len(erros), erros)
        self.assertIn(trecho, erros[0])

    def _com_teste_de(self, n: int) -> ouro.Manifesto:
        m = _teste_valido()
        teste = [x for x in m.livros if x.split == ouro.TESTE]
        ficam = [teste[10], teste[11], *teste[: n - 2]]  # por, spa e inglês: só o tamanho pode falhar
        ids = {x.identidade for x in ficam}
        dev = [x for x in m.livros if x.split == ouro.DEV]
        return _manifesto(ficam + dev, [f for f in m.folhas if f.identidade in ids or f.split == ouro.DEV])

    def test_o_minimo_do_teste_e_oito(self) -> None:
        self.assertEqual(8, ouro.TESTE_MINIMO)
        self._so(self._com_teste_de(7), "o teste tem 7 livros")
        self.assertEqual([], ouro.problemas(self._com_teste_de(8)))

    def test_datas_fora_do_formato(self) -> None:
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), list(m.folhas), congelado_em="30/10/2026"), "congelado_em")
        self._so(_manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="02/11/2026"), "foi lido")

    def test_formato_da_leitura_sozinho(self) -> None:
        """`2026/11/02` vem depois de `2026-10-30` na ordem das strings: só o formato o pega."""
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="2026/11/02"), "foi lido")

    def test_ler_no_dia_do_congelamento_vale(self) -> None:
        m = _teste_valido()
        self.assertEqual([], ouro.problemas(_manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="2026-10-30")))

    def test_reprovado_no_teste_mesmo_fora_do_treino(self) -> None:
        m = _teste_valido()
        livros = [L(x.identidade, x.split, x.lingua, fora_do_treino=True, reprovado="auditoria: x")
                  if x.identidade == _id(0) else x for x in m.livros]
        self._so(_manifesto(livros, list(m.folhas)), "reprovado")

    def test_reprovado_na_reserva_dentro_do_treino(self) -> None:
        m = _teste_valido()
        self._so(_manifesto([*m.livros, L(_id(71), ouro.RESERVA, "eng", reprovado="auditoria: x")], list(m.folhas)),
                 "reprovado")

    def test_origem_e_diagramacao_invalidas(self) -> None:
        m = _teste_valido()
        self._so(_manifesto([*m.livros, L(_id(72), ouro.RESERVA, "eng", origem="")], list(m.folhas)), "origem ''")
        self._so(_manifesto([*m.livros, L(_id(73), ouro.RESERVA, "eng", diagramacao="outra")], list(m.folhas)),
                 "diagramação 'outra'")

    def test_data_com_lixo_no_fim(self) -> None:
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), list(m.folhas), congelado_em="2026-10-30x"), "congelado_em")
        self._so(_manifesto(list(m.livros), list(m.folhas), primeira_leitura_do_teste="2026-11-02x"), "foi lido")

    def test_lingua_fora_da_lista_e_folha_noutra_lingua(self) -> None:
        m = _teste_valido()
        self._so(_manifesto([*m.livros, L(_id(74), ouro.RESERVA, "en")], list(m.folhas)), "língua 'en'")
        self._so(_manifesto(list(m.livros), [*m.folhas, F(_id(0), 300, "por", ouro.PROSA, ouro.TESTE)]), "em 'por'")

    def test_as_linguas_sao_as_oito_do_acervo(self) -> None:
        self.assertEqual(("eng", "por", "spa", "deu", "nld", "fra", "ron", "rus"), ouro.LINGUAS)

    def test_folha_dev_noutra_lingua(self) -> None:
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), [*m.folhas, F(_id(99), 300, "por", ouro.PROSA, ouro.DEV)]), "em 'por'")

    def test_formato_de_entrou_em(self) -> None:
        """`2026/11/05` vem depois de `2026-10-30` na ordem das strings: só o formato o pega."""
        m = _teste_valido()
        for data in ("2026/11/05", "2026-11-05x"):
            with self.subTest(data=data):
                livros = [L(x.identidade, x.split, x.lingua, entrou_em=data) if x.identidade == _id(0) else x
                          for x in m.livros]
                self._so(_manifesto(livros, list(m.folhas)), "entrou_em")

    def test_entrar_no_dia_do_congelamento_vale(self) -> None:
        m = _teste_valido()
        livros = [L(x.identidade, x.split, x.lingua, entrou_em="2026-10-30") if x.identidade == _id(0) else x
                  for x in m.livros]
        self.assertEqual([], ouro.problemas(_manifesto(livros, list(m.folhas))))

    def test_o_representante_da_serie_na_reserva_quando_o_livro_do_teste_e_membro(self) -> None:
        """A configuração que o `--serie` cria: o livro do teste aponta o representante, que fica na reserva."""
        m = _teste_valido()
        livros = [L(x.identidade, x.split, x.lingua, grupo=_id(260)) if x.identidade == _id(0) else x for x in m.livros]
        self._so(_manifesto([*livros, L(_id(260), ouro.RESERVA, "eng")], list(m.folhas)), "fora_do_treino")

    def test_entrou_em_so_no_teste_e_depois_do_congelamento(self) -> None:
        m = _teste_valido()
        self._so(_manifesto([*m.livros, L(_id(75), ouro.RESERVA, "eng", entrou_em="2026-11-05")], list(m.folhas)),
                 "entrou_em")
        cedo = [L(x.identidade, x.split, x.lingua, entrou_em="2026-10-29") if x.identidade == _id(0) else x
                for x in m.livros]
        self._so(_manifesto(cedo, list(m.folhas)), "entrou_em")

    def test_irmao_pelo_grupo_do_livro_do_teste(self) -> None:
        """O livro do teste é membro da série `G`; o irmão da reserva, também membro, tem de sair do treino."""
        m = _teste_valido()
        livros = [L(x.identidade, x.split, x.lingua, grupo=_id(250)) if x.identidade == _id(0) else x for x in m.livros]
        self._so(_manifesto([*livros, L(_id(251), ouro.RESERVA, "eng", grupo=_id(250))], list(m.folhas)),
                 "fora_do_treino")

    def test_versao(self) -> None:
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), list(m.folhas), versao=2), "versão 2")

    def test_livro_sem_identidade_e_split_invalido(self) -> None:
        m = _teste_valido()
        self._so(_manifesto([*m.livros, L("", ouro.RESERVA, "eng")], list(m.folhas)), "livro sem identidade")
        self._so(_manifesto([*m.livros, L(_id(70), "treino", "eng")], list(m.folhas)), "split 'treino'")

    def test_estrato_invalido_folha_zero_e_repetida(self) -> None:
        m = _teste_valido()
        base = list(m.folhas)
        self._so(_manifesto(list(m.livros), [*base, F(_id(99), 300, "eng", "titulo", ouro.DEV)]), "estrato 'titulo'")
        self._so(_manifesto(list(m.livros), [*base, F(_id(99), 0, "eng", ouro.PROSA, ouro.DEV)]), "base 1")
        self._so(_manifesto(list(m.livros), [*base, base[0]]), "repetida")

    def test_livro_do_teste_sem_folha(self) -> None:
        m = _teste_valido()
        self._so(_manifesto(list(m.livros), [f for f in m.folhas if f.identidade != _id(3)]), "sem folha")

    def test_livro_do_teste_com_diagramacao_de_livro_dev(self) -> None:
        m = _teste_valido()
        livros = [L(x.identidade, x.split, x.lingua, diagramacao="vista") if x.identidade == _id(2) else x
                  for x in m.livros]
        self._so(_manifesto(livros, list(m.folhas)), "diagramação de livro dev")


class CaminhoTests(unittest.TestCase):
    def test_o_manifesto_e_lido_da_raiz_do_pacote(self) -> None:
        """Num checkout, `BUNDLE_ROOT` é a raiz do repositório; no instalador, a pasta do pacote."""
        with mock.patch.object(ouro, "BUNDLE_ROOT", Path("X:/pacote")):
            self.assertEqual(Path("X:/pacote") / "assets" / "texto_prosa" / "ouro.json", ouro.caminho_padrao())


class LocalizarTests(unittest.TestCase):
    def test_so_os_procurados_e_o_primeiro_de_dois_iguais(self) -> None:
        with TemporaryDirectory() as tmp:
            for nome, conteudo in (("a.pdf", b"livro um"), ("b.pdf", b"livro um"), ("c.pdf", b"outro livro")):
                (Path(tmp) / nome).write_bytes(b"%PDF-1.4 " + conteudo * 50)
            procurado = ouro.identidade_de(Path(tmp) / "a.pdf")
            self.assertEqual({procurado: Path(tmp) / "a.pdf"}, ouro.localizar([procurado], [tmp]))

    def test_acha_pela_identidade_mesmo_renomeado(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "livro.pdf"
            pdf.write_bytes(b"%PDF-1.4 conteudo do livro" * 100)
            identidade = ouro.identidade_de(pdf)
            novo = pdf.with_name("outro nome.pdf")
            pdf.rename(novo)
            self.assertEqual({identidade: novo}, ouro.localizar([identidade, _id(1)], [tmp, Path(tmp) / "nao_existe"]))


class VersionadoTests(unittest.TestCase):
    """O manifesto do repositório: é ele que decide os portões, e ele tem de valer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = ouro.carregar(ouro.caminho_padrao())

    def test_o_manifesto_versionado_vale(self) -> None:
        self.assertEqual([], ouro.problemas(self.m))

    def test_teste_tem_doze_livros(self) -> None:
        self.assertGreaterEqual(sum(x.split == ouro.TESTE for x in self.m.livros), 12)

    def test_a_terceira_lingua_e_a_unica_pendencia(self) -> None:
        """Congelado em 2026-10-30 com inglês e português: o livro em espanhol da D6 não tinha folha de
        prosa, e o dono traz o da terceira língua depois (ver `ouro.PENDENCIA_DE_LINGUA`). Quando ele
        entrar, a pendência sai e este teste passa a pedir as três línguas."""
        linguas = {x.lingua for x in self.m.livros if x.split == ouro.TESTE}
        if ouro.PENDENCIA_DE_LINGUA in self.m.pendencias:
            self.assertEqual({"eng", "por"}, linguas)
        else:
            self.assertGreaterEqual(len(linguas), 3)
        self.assertLessEqual(set(self.m.pendencias), {ouro.PENDENCIA_DE_LINGUA})

    def test_todo_livro_do_teste_tem_seis_folhas(self) -> None:
        por_livro: dict[str, int] = {}
        for folha in self.m.do_split(ouro.TESTE):
            por_livro[folha.identidade] = por_livro.get(folha.identidade, 0) + 1
        self.assertTrue(por_livro)
        self.assertEqual({6}, set(por_livro.values()))

    def test_o_dev_sao_os_livros_de_2026_10_30_que_passaram_na_auditoria(self) -> None:
        """Eram sete; a auditoria visual reprovou dois (a ligadura ft que perde o t, figurinas fora da
        linha da camada), e a referência deles não é a tinta."""
        self.assertEqual(5, sum(x.split == ouro.DEV for x in self.m.livros))

    def test_todo_reprovado_diz_o_motivo_da_auditoria(self) -> None:
        reprovados = [x for x in self.m.livros if x.reprovado]
        self.assertTrue(reprovados)
        self.assertTrue(all(x.reprovado.startswith("auditoria: ") for x in reprovados))

    def test_gravar_reproduz_o_arquivo_byte_a_byte(self) -> None:
        with TemporaryDirectory() as tmp:
            copia = Path(tmp) / "ouro.json"
            ouro.gravar(self.m, copia)
            self.assertEqual(ouro.caminho_padrao().read_bytes(), copia.read_bytes())

    def test_o_sorteio_gravado_e_o_do_codigo(self) -> None:
        self.assertEqual({"prosa": list(ouro.ESTRATO_PROSA), "misto": list(ouro.ESTRATO_MISTO)}, self.m.sorteio["estratos"])

    def test_os_reprovados_sao_os_do_arquivo_da_auditoria(self) -> None:
        tsv = ouro.caminho_padrao().parents[2] / "docs" / "metrics" / "texto_ouro_2026-10-30" / "reprovados_auditoria.tsv"
        do_arquivo = {}
        for linha in tsv.read_text(encoding="utf-8").splitlines():
            if linha and not linha.startswith("#"):
                identidade, motivo = linha.split("\t", 1)
                do_arquivo[identidade] = motivo
        self.assertEqual(do_arquivo, {x.identidade: x.reprovado for x in self.m.livros if x.reprovado})

    def test_o_teste_nao_foi_lido(self) -> None:
        """Muda no dia em que a S-706 abrir o teste -- e então a data tem de ser posterior."""
        self.assertIsNone(self.m.primeira_leitura_do_teste)


if __name__ == "__main__":
    unittest.main()
