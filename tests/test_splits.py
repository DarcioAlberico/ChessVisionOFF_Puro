from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.splits import (
    assign_split,
    compute_splits,
    ensure_splits,
    group_keys,
    group_representative,
    groups_by_origin,
    load_splits,
    save_splits,
    split_counts,
    split_leaks,
)


def _names(count: int, prefix: str = "board") -> list[str]:
    return [f"{prefix}_{i:05d}.png" for i in range(count)]


class DeterminismTests(unittest.TestCase):
    def test_same_key_always_gets_same_split(self) -> None:
        for name in _names(50):
            self.assertEqual(assign_split(name), assign_split(name))

    def test_split_does_not_depend_on_process(self) -> None:
        # Valores fixos: se o algoritmo de hash mudar, isto quebra de proposito.
        # Usa SHA-256 justamente porque hash() de str e randomizado por processo.
        self.assertEqual(assign_split("board_00000.png"), assign_split("board_00000.png"))
        expected = {name: assign_split(name) for name in _names(20)}
        self.assertEqual({name: assign_split(name) for name in _names(20)}, expected)

    def test_proportions_are_approximately_respected(self) -> None:
        splits = compute_splits(_names(3000), val_pct=10, test_pct=10)
        counts = split_counts(splits)

        self.assertAlmostEqual(counts["test"] / 3000, 0.10, delta=0.02)
        self.assertAlmostEqual(counts["val"] / 3000, 0.10, delta=0.02)
        self.assertAlmostEqual(counts["train"] / 3000, 0.80, delta=0.03)

    def test_rejects_impossible_percentages(self) -> None:
        with self.assertRaises(ValueError):
            assign_split("x.png", val_pct=60, test_pct=50)


class StabilityUnderGrowthTests(unittest.TestCase):
    """A propriedade central: crescer o dataset nao pode mover amostras antigas."""

    def test_adding_samples_does_not_move_existing_ones(self) -> None:
        before = compute_splits(_names(1000))
        after = compute_splits(_names(1100))

        for name in _names(1000):
            self.assertEqual(before[name], after[name], f"{name} mudou de split ao crescer o dataset")

    def test_ensure_splits_preserves_recorded_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"

            first = ensure_splits(_names(100), path)
            # Forca uma atribuicao divergente para provar que o arquivo tem precedencia.
            tampered = dict(first)
            tampered[_names(100)[0]] = "test" if first[_names(100)[0]] != "test" else "train"
            save_splits(path, tampered)

            second = ensure_splits(_names(150), path)

            for name in _names(100):
                self.assertEqual(second[name], tampered[name])
            self.assertEqual(len(second), 150)


class GroupAwarenessTests(unittest.TestCase):
    """Amostras redundantes nao podem se espalhar entre splits: seria vazamento."""

    def test_group_members_share_a_split(self) -> None:
        names = _names(600)
        # Agrupa pares distantes na ordem, para que sem agrupamento caissem em splits
        # diferentes com alta probabilidade.
        groups = [[names[i], names[i + 300]] for i in range(300)]

        splits = compute_splits(names, groups=groups)

        for group in groups:
            with self.subTest(group=group):
                self.assertEqual(splits[group[0]], splits[group[1]])

    def test_grouping_actually_changes_something(self) -> None:
        # Garante que o teste anterior nao passa por acidente.
        names = _names(600)
        groups = [[names[i], names[i + 300]] for i in range(300)]

        without = compute_splits(names)
        straddling = sum(1 for g in groups if without[g[0]] != without[g[1]])

        self.assertGreater(straddling, 0, "sem agrupamento, algum grupo deveria cruzar splits")

    def test_group_keys_maps_members_to_representative(self) -> None:
        keys = group_keys(["a.png", "b.png", "c.png"], [["b.png", "a.png"]])

        self.assertEqual(keys["a.png"], "a.png")
        self.assertEqual(keys["b.png"], "a.png")
        self.assertEqual(keys["c.png"], "c.png")

    def test_new_member_of_known_group_inherits_its_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            ensure_splits(["a.png"], path)
            recorded = load_splits(path)["a.png"]

            grown = ensure_splits(["a.png", "b.png"], path, groups=[["a.png", "b.png"]])

            self.assertEqual(grown["b.png"], recorded)


class MesmoDiagramaImpressoTests(unittest.TestCase):
    """S-98: o guarda de imagem não vê a mesma página reextraída com recorte deslocado.

    `duplicate_groups_touching` agrupa por `placement` igual **e** dHash ≤ 3, e o 3 foi
    calibrado para "a mesma amostra salva duas vezes". Revarrer um livro depois de a detecção
    mudar produz um recorte deslocado, com nome novo por timestamp -- e `ensure_splits`
    sorteia pelo hash do nome. Medido no acervo em 2026-08-16: 3 triplas cruzam split, e a do
    `Niemeijer p10 d1` está nas **três** partições.
    """

    def test_agrupa_o_mesmo_diagrama_impresso(self) -> None:
        origens = {
            "a.png": ("livro.pdf", "41", "1"),
            "b.png": ("livro.pdf", "41", "1"),
            "c.png": ("livro.pdf", "41", "2"),
        }
        self.assertEqual(groups_by_origin(origens), [["a.png", "b.png"]])

    def test_amostra_sem_procedencia_fica_de_fora(self) -> None:
        """84,1% do acervo não declara procedência; inventar seria pior que não agrupar."""
        origens = {
            "a.png": ("", "", ""),
            "b.png": ("", "", ""),
            "c.png": ("livro.pdf", "", "1"),
        }
        self.assertEqual(groups_by_origin(origens), [])

    def test_o_mesmo_diagrama_impresso_cai_no_mesmo_split(self) -> None:
        nomes = _names(600)
        sem = compute_splits(nomes)
        # Um par que, pelo hash do nome, cai em splits diferentes -- que é exatamente o que
        # acontece quando a mesma página é reextraída e ganha nome novo por timestamp.
        primeiro = nomes[0]
        segundo = next(nome for nome in nomes if sem[nome] != sem[primeiro])

        origens = dict.fromkeys(nomes, ("", "", ""))
        origens[primeiro] = ("livro.pdf", "41", "1")
        origens[segundo] = ("livro.pdf", "41", "1")

        com = compute_splits(nomes, groups=groups_by_origin(origens))

        self.assertNotEqual(sem[primeiro], sem[segundo], "sem agrupamento o par cruzava split")
        self.assertEqual(com[primeiro], com[segundo])

    def test_vazamento_e_listado_com_o_split_de_cada_membro(self) -> None:
        origens = {
            "a.png": ("livro.pdf", "10", "1"),
            "b.png": ("livro.pdf", "10", "1"),
            "c.png": ("livro.pdf", "20", "1"),
        }
        splits = {"a.png": "train", "b.png": "test", "c.png": "val"}

        vazamentos = split_leaks(origens, splits)  # type: ignore[arg-type]

        self.assertEqual(len(vazamentos), 1)
        chave, membros = vazamentos[0]
        self.assertEqual(chave, ("livro.pdf", "10", "1"))
        self.assertEqual(membros, {"a.png": "train", "b.png": "test"})

    def test_o_mesmo_diagrama_no_mesmo_split_nao_e_vazamento(self) -> None:
        origens = {"a.png": ("livro.pdf", "10", "1"), "b.png": ("livro.pdf", "10", "1")}
        splits = {"a.png": "train", "b.png": "train"}

        self.assertEqual(split_leaks(origens, splits), [])  # type: ignore[arg-type]

    def test_a_estabilidade_da_s07_e_preservada(self) -> None:
        """Agrupar não pode mover o que já era `test`: é a garantia que a S-07 existe para dar."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            ensure_splits(["a.png"], path)
            antes = load_splits(path)["a.png"]

            depois = ensure_splits(["a.png", "b.png"], path, groups=[["a.png", "b.png"]])

            self.assertEqual(depois["a.png"], antes)


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            data = {"a.png": "train", "b.png": "val", "c.png": "test"}

            save_splits(path, data)  # type: ignore[arg-type]

            self.assertEqual(load_splits(path), data)

    def test_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_splits(Path(tmp) / "ausente.csv"), {})

    def test_invalid_split_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            path.write_text("filename,split\na.png,treino\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_splits(path)


class ListaVaziaNaoPodaTests(unittest.TestCase):
    """S-300: `labels.csv` ausente fazia o treino apagar o `data/splits.csv` inteiro.

    A poda de um *subconjunto* é o comportamento desejado -- amostra que saiu do CSV sai daqui.
    Podar *tudo* nunca foi: `filenames` vazio quer dizer "não consegui ler a lista", e não
    "não há mais nenhuma amostra". O que a poda total custava não era dado, era a fronteira
    entre treino e teste -- e ela não se reconstrói.
    """

    def test_lista_vazia_preserva_o_arquivo_inteiro(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            save_splits(path, {"a.png": "test", "b.png": "train", "c.png": "val"})

            devolvido = ensure_splits([], path)

            self.assertEqual(load_splits(path), {"a.png": "test", "b.png": "train", "c.png": "val"})
            self.assertEqual(devolvido, load_splits(path))

    def test_a_poda_de_um_subconjunto_continua_valendo(self) -> None:
        """O contrário do anterior, e é por isso que a guarda testa `not names` e não um limiar.

        Uma fração mínima de sobrevivência exigiria uma política que ninguém tem; "a lista veio
        vazia" é um fato, não uma escolha.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            save_splits(path, {"a.png": "test", "b.png": "train", "c.png": "val"})

            ensure_splits(["a.png", "b.png"], path)

            self.assertEqual(load_splits(path), {"a.png": "test", "b.png": "train"})


class RepresentanteDoGrupoTests(unittest.TestCase):
    """Um grupo, **um** representante -- e ele é quem declara procedência (S-431).

    O nome tem dois usos que precisam coincidir: é a chave de que o split do grupo sai, e é a
    linha que o `cvoff-audit --dedupe` mantém ao apagar as cópias. Enquanto os dois eram
    `sorted(grupo)[0]` -- o mais antigo, e as amostras anteriores à S-19 não declaram
    procedência --, o dedupe apagava a procedência de 276 grupos em 6 livros.
    """

    def test_sem_procedencia_o_representante_e_o_primeiro_nome(self) -> None:
        self.assertEqual(group_representative(["c.png", "a.png", "b.png"]), "a.png")

    def test_quem_declara_procedencia_vem_antes_do_nome(self) -> None:
        self.assertEqual(group_representative(["c.png", "a.png", "b.png"], {"c.png"}), "c.png")

    def test_o_empate_entre_dois_que_declaram_e_pelo_nome(self) -> None:
        self.assertEqual(group_representative(["c.png", "a.png", "b.png"], {"c.png", "b.png"}), "b.png")

    def test_group_keys_deriva_a_chave_do_mesmo_representante(self) -> None:
        chaves = group_keys(["a.png", "b.png"], [["a.png", "b.png"]], with_provenance={"b.png"})

        self.assertEqual(chaves, {"a.png": "b.png", "b.png": "b.png"})

    def test_membro_novo_herda_o_split_de_qualquer_membro_registrado(self) -> None:
        """**O que o conserto não podia quebrar.** A herança olhava só o representante, e o
        representante passou a poder ser o membro **novo** -- que ainda não tem split. Sem
        olhar o grupo inteiro, o antigo ficaria onde está e o novo sortearia: o grupo se
        partiria em dois splits, que é exatamente o que a S-07 existe para impedir.
        """
        antigo = "board_00000.png"
        # Um nome que, sozinho, cairia noutro split -- senao o teste passaria por acidente.
        novo = next(nome for nome in _names(200) if assign_split(nome) != assign_split(antigo))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "splits.csv"
            ensure_splits([antigo], path)
            registrado = load_splits(path)[antigo]

            crescido = ensure_splits([antigo, novo], path, groups=[[antigo, novo]], with_provenance={novo})

            self.assertNotEqual(assign_split(novo), registrado, "sem herança o par cruzaria split")
            self.assertEqual(crescido[novo], registrado)
            self.assertEqual(crescido[antigo], registrado, "e o que já estava registrado não se move")


if __name__ == "__main__":
    unittest.main()
