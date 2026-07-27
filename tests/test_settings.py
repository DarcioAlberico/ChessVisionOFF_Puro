"""Configuração do usuário e o opt-in da correção remota (S-32).

O critério de aceite pede duas coisas verificáveis: sem configuração o botão fica
desabilitado com explicação, e **nenhuma requisição de rede parte do app em uso padrão**.
A segunda é a que este arquivo trava de forma que não dependa de ninguém lembrar.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np

from chess_diagram_ocr.net_correction import (
    HttpFenProvider,
    RemoteFenProvider,
    build_provider,
)
from chess_diagram_ocr.settings import (
    ENV_REMOTE_ENABLED,
    ENV_REMOTE_URL,
    RemoteFenSettings,
    Settings,
    apply_environment,
    load_settings,
    save_settings,
)

ENDPOINT = "https://exemplo.invalido/predict"


class DefaultTests(unittest.TestCase):
    def test_the_default_sends_nothing(self) -> None:
        padrao = Settings().remote_fen
        self.assertFalse(padrao.enabled)
        self.assertEqual(padrao.endpoint, "")
        self.assertFalse(padrao.is_usable)

    def test_there_is_no_built_in_endpoint_to_fall_back_to(self) -> None:
        """Um endpoint padrão faria o recurso voltar a existir sem ninguém pedir."""
        self.assertIsNone(build_provider(Settings().remote_fen))

    def test_enabled_without_an_endpoint_is_still_not_usable(self) -> None:
        """Ligado e sem destino não é uma configuração: é uma configuração pela metade."""
        self.assertFalse(RemoteFenSettings(enabled=True).is_usable)
        self.assertIsNone(build_provider(RemoteFenSettings(enabled=True)))

    def test_an_endpoint_without_being_enabled_is_not_usable(self) -> None:
        self.assertFalse(RemoteFenSettings(endpoint=ENDPOINT).is_usable)

    def test_both_together_are(self) -> None:
        configuracao = RemoteFenSettings(enabled=True, endpoint=ENDPOINT)
        self.assertTrue(configuracao.is_usable)
        self.assertIsInstance(build_provider(configuracao), HttpFenProvider)


class NoNetworkByDefaultTests(unittest.TestCase):
    """O critério de aceite da S-32, na forma em que ele é uma prova e não uma promessa."""

    def test_no_request_can_be_built_from_the_default_configuration(self) -> None:
        with mock.patch("urllib.request.urlopen") as urlopen:
            provedor = build_provider(load_settings(Path("nao-existe.json"), env={}).remote_fen)
            self.assertIsNone(provedor)
        urlopen.assert_not_called()

    def test_the_environment_can_force_the_feature_off_over_the_file(self) -> None:
        """Um script ou a CI garantem que nada sai sem depender do que está em disco."""
        gravado = Settings(remote_fen=RemoteFenSettings(enabled=True, endpoint=ENDPOINT))
        resultado = apply_environment(gravado, env={ENV_REMOTE_ENABLED: "0"})

        self.assertFalse(resultado.remote_fen.is_usable)
        self.assertIsNone(build_provider(resultado.remote_fen))


class EnvironmentTests(unittest.TestCase):
    def test_an_endpoint_from_the_environment_enables_the_feature(self) -> None:
        """Informar o endereço já é a declaração explícita; exigir duas variáveis seria ruído."""
        resultado = apply_environment(Settings(), env={ENV_REMOTE_URL: ENDPOINT})
        self.assertTrue(resultado.remote_fen.is_usable)
        self.assertEqual(resultado.remote_fen.endpoint, ENDPOINT)

    def test_the_environment_endpoint_wins_over_the_file(self) -> None:
        gravado = Settings(remote_fen=RemoteFenSettings(enabled=True, endpoint="http://antigo/x"))
        resultado = apply_environment(gravado, env={ENV_REMOTE_URL: ENDPOINT})
        self.assertEqual(resultado.remote_fen.endpoint, ENDPOINT)

    def test_an_explicit_on_beats_a_file_that_says_off(self) -> None:
        gravado = Settings(remote_fen=RemoteFenSettings(enabled=False, endpoint=ENDPOINT))
        self.assertTrue(apply_environment(gravado, env={ENV_REMOTE_ENABLED: "1"}).remote_fen.is_usable)

    def test_an_unrecognised_value_changes_nothing(self) -> None:
        gravado = Settings(remote_fen=RemoteFenSettings(enabled=True, endpoint=ENDPOINT))
        self.assertTrue(apply_environment(gravado, env={ENV_REMOTE_ENABLED: "talvez"}).remote_fen.is_usable)


class MessageTests(unittest.TestCase):
    def test_the_tooltip_distinguishes_unconfigured_from_switched_off(self) -> None:
        """São situações diferentes e a saída de cada uma é diferente."""
        sem_config = RemoteFenSettings().disabled_reason()
        desligado = RemoteFenSettings(endpoint=ENDPOINT).disabled_reason()

        self.assertIn("nao configurada", sem_config.replace("ã", "a").replace("ç", "c"))
        self.assertIn(ENV_REMOTE_URL, sem_config)
        self.assertIn("exemplo.invalido", desligado)
        self.assertNotEqual(sem_config, desligado)

    def test_a_working_configuration_has_nothing_to_explain(self) -> None:
        self.assertEqual(RemoteFenSettings(enabled=True, endpoint=ENDPOINT).disabled_reason(), "")

    def test_the_consent_message_names_the_host_it_will_send_to(self) -> None:
        """"Um serviço externo" não é informação; o host é."""
        mensagem = RemoteFenSettings(enabled=True, endpoint=ENDPOINT).consent_message()
        self.assertIn("exemplo.invalido", mensagem)

    def test_the_host_is_extracted_from_the_url(self) -> None:
        self.assertEqual(RemoteFenSettings(endpoint=ENDPOINT).host, "exemplo.invalido")


class PersistenceTests(unittest.TestCase):
    def test_settings_round_trip_through_the_file(self) -> None:
        original = Settings(
            remote_fen=RemoteFenSettings(enabled=True, endpoint=ENDPOINT, timeout=7.5, acknowledged=True)
        )
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "settings.json"
            save_settings(caminho, original)
            self.assertEqual(load_settings(caminho, env={}), original)

    def test_a_corrupt_file_falls_back_to_the_default_which_sends_nothing(self) -> None:
        """Falhar para o lado do padrão é seguro porque o padrão é "desligado"."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "settings.json"
            caminho.write_text("{ isto nao e json", encoding="utf-8")
            self.assertFalse(load_settings(caminho, env={}).remote_fen.is_usable)

    def test_a_file_that_is_not_an_object_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "settings.json"
            caminho.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertFalse(load_settings(caminho, env={}).remote_fen.is_usable)

    def test_the_written_file_carries_a_version(self) -> None:
        """Sem versão, um esquema novo não teria como distinguir "campo ausente" de "antigo"."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "settings.json"
            save_settings(caminho, Settings())
            self.assertIn("version", json.loads(caminho.read_text(encoding="utf-8")))

    def test_acknowledging_is_what_the_dialog_persists(self) -> None:
        configuracao = RemoteFenSettings(enabled=True, endpoint=ENDPOINT)
        self.assertFalse(configuracao.acknowledged)
        self.assertTrue(replace(configuracao, acknowledged=True).acknowledged)


class ProviderTests(unittest.TestCase):
    def test_a_provider_without_an_endpoint_refuses_to_exist(self) -> None:
        """Deixá-lo existir é o que faria a interface oferecer o botão."""
        with self.assertRaises(ValueError):
            HttpFenProvider("   ")

    def test_the_provider_reports_where_it_sends_to(self) -> None:
        self.assertEqual(HttpFenProvider(ENDPOINT).name, ENDPOINT)

    def test_a_local_second_opinion_satisfies_the_same_protocol(self) -> None:
        """A S-32 pede provedor plugável; um segundo modelo local não deve herdar de HTTP."""

        class _Local:
            @property
            def name(self) -> str:
                return "modelo local"

            def predict(self, image_rgb: np.ndarray) -> str:
                return "8/8/8/8/8/8/8/K6k"

        self.assertIsInstance(_Local(), RemoteFenProvider)

    def test_the_provider_uses_the_configured_endpoint_and_timeout(self) -> None:
        configuracao = RemoteFenSettings(enabled=True, endpoint=ENDPOINT, timeout=3)
        provedor = build_provider(configuracao)
        assert provedor is not None

        class _Response:
            def read(self) -> bytes:
                return b'{"results": [{"fen": "8/8/8/8/8/8/8/K6k"}]}'

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        board = np.zeros((64, 64, 3), dtype=np.uint8)
        with mock.patch("urllib.request.urlopen", return_value=_Response()) as chamada:
            provedor.predict(board)

        self.assertEqual(chamada.call_args.args[0].full_url, ENDPOINT)
        self.assertEqual(chamada.call_args.kwargs["timeout"], 3)


if __name__ == "__main__":
    unittest.main()
