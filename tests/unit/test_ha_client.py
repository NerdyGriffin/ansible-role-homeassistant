"""Offline tests for module_utils/ha_client.py.

Nothing here touches a Home Assistant instance. The live checks live in
tests/integration/test_modules.yml, which needs a real server and a token.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "module_utils")
)

from ha_client import HomeAssistantClient  # noqa: E402


class TestReplaceReferences:
    """The word-boundary behaviour is the whole point of this helper: a naive
    string replace turns sensor.foo into sensor.bar inside sensor.foobar."""

    def test_replaces_a_whole_reference(self):
        data = {"entity_id": "sensor.foo"}
        assert HomeAssistantClient.replace_references(data, "sensor.foo", "sensor.bar")
        assert data == {"entity_id": "sensor.bar"}

    def test_does_not_replace_a_longer_id_that_starts_the_same(self):
        data = {"entity_id": "sensor.foobar"}
        assert not HomeAssistantClient.replace_references(
            data, "sensor.foo", "sensor.bar"
        )
        assert data == {"entity_id": "sensor.foobar"}

    def test_does_not_replace_across_a_dotted_suffix(self):
        data = {"entity_id": "sensor.foo.attribute"}
        assert not HomeAssistantClient.replace_references(
            data, "sensor.foo", "sensor.bar"
        )

    def test_recurses_into_lists_and_nested_dicts(self):
        data = {
            "action": [
                {"target": {"entity_id": ["sensor.foo", "sensor.other"]}},
                {"target": {"entity_id": "sensor.foo"}},
            ]
        }
        assert HomeAssistantClient.replace_references(data, "sensor.foo", "sensor.bar")
        assert data["action"][0]["target"]["entity_id"] == ["sensor.bar", "sensor.other"]
        assert data["action"][1]["target"]["entity_id"] == "sensor.bar"

    def test_replaces_a_reference_embedded_in_a_template(self):
        data = {"value_template": "{{ states('sensor.foo') }}"}
        assert HomeAssistantClient.replace_references(data, "sensor.foo", "sensor.bar")
        assert data["value_template"] == "{{ states('sensor.bar') }}"

    def test_reports_no_change_when_nothing_matches(self):
        data = {"entity_id": "sensor.unrelated"}
        assert not HomeAssistantClient.replace_references(
            data, "sensor.foo", "sensor.bar"
        )


class TestFromAnsibleParams:
    def test_reads_a_bare_connection_dict(self):
        client = HomeAssistantClient.from_ansible_params(
            {"host": "ha.example.com", "port": 8443, "access_token": "t"}
        )
        assert client.host == "ha.example.com"
        assert client.port == 8443
        assert client.access_token == "t"

    def test_reads_a_dict_wrapped_under_homeassistant(self):
        client = HomeAssistantClient.from_ansible_params(
            {"homeassistant": {"host": "ha.example.com", "access_token": "t"}}
        )
        assert client.host == "ha.example.com"
        assert client.access_token == "t"

    def test_applies_defaults_for_omitted_settings(self):
        client = HomeAssistantClient.from_ansible_params({"host": "ha.example.com"})
        assert client.port == 8123
        assert client.tls is False
        assert client.ssl_verify is False


class TestUrlDerivation:
    def test_plain_http_by_default(self):
        client = HomeAssistantClient("ha.example.com")
        assert client._base_url == "http://ha.example.com:8123"

    def test_https_when_tls_is_set(self):
        client = HomeAssistantClient("ha.example.com", port=8443, tls=True)
        assert client._base_url == "https://ha.example.com:8443"


def test_check_dependencies_returns_a_list():
    """Whatever is installed in CI, the contract is a list of package names."""
    import ha_client

    missing = ha_client.check_dependencies()
    assert isinstance(missing, list)
    assert all(isinstance(name, str) for name in missing)
