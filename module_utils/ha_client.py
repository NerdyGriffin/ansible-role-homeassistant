"""
Home Assistant WebSocket and REST API client for Ansible modules.

Provides connection management, authentication, and typed helpers for
interacting with the HA entity registry, automation config, dashboard
config, script config, and device registry.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import re
import ssl

try:
    import websocket as websocket_lib
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def check_dependencies():
    """Return list of missing Python dependencies."""
    missing = []
    if not HAS_WEBSOCKET:
        missing.append('websocket-client')
    if not HAS_REQUESTS:
        missing.append('requests')
    return missing


class HomeAssistantClient:
    """Client for Home Assistant WebSocket and REST APIs."""

    def __init__(self, host, port=8123, access_token=None, tls=False, ssl_verify=False):
        self.host = host
        self.port = port
        self.access_token = access_token
        self.tls = tls
        self.ssl_verify = ssl_verify
        self._ws = None
        self._msg_id = 0
        self._tls_s = "s" if tls else ""
        self._base_url = "http{s}://{host}:{port}".format(
            s=self._tls_s, host=host, port=port
        )

    @classmethod
    def from_ansible_params(cls, params):
        """Create client from Ansible module params (homeassistant dict)."""
        ha = params.get('homeassistant', params)
        return cls(
            host=ha.get('host', 'homeassistant.local'),
            port=ha.get('port', 8123),
            access_token=ha.get('access_token', ''),
            tls=ha.get('tls', False),
            ssl_verify=ha.get('ssl_verify', False),
        )

    # ──────────────────────────────────────────────
    # Connection management
    # ──────────────────────────────────────────────

    def connect(self):
        """Establish and authenticate a WebSocket connection."""
        ws_url = "ws{s}://{host}:{port}/api/websocket".format(
            s=self._tls_s, host=self.host, port=self.port
        )
        sslopt = {"cert_reqs": ssl.CERT_NONE} if not self.ssl_verify else {}
        self._ws = websocket_lib.WebSocket(sslopt=sslopt)
        self._ws.connect(ws_url)

        # Server sends auth_required
        self._ws.recv()

        # Authenticate
        auth_msg = json.dumps({
            "type": "auth",
            "access_token": self.access_token
        })
        self._ws.send(auth_msg)
        result = json.loads(self._ws.recv())
        if result.get("type") != "auth_ok":
            self.close()
            raise RuntimeError("Authentication failed. Check your access token.")
        return self

    def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            self._ws.close()
            self._ws = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _send(self, msg_type, **kwargs):
        """Send a WebSocket message and return the result."""
        self._msg_id += 1
        payload = {"id": self._msg_id, "type": msg_type}
        payload.update(kwargs)
        self._ws.send(json.dumps(payload))
        result = json.loads(self._ws.recv())
        if not result.get("success", False):
            error = result.get("error", {})
            raise RuntimeError(
                "HA API error ({code}): {message}".format(
                    code=error.get("code", "unknown"),
                    message=error.get("message", str(result))
                )
            )
        return result.get("result")

    def _http_headers(self):
        """Return HTTP headers for REST API calls."""
        return {
            "Authorization": "Bearer {token}".format(token=self.access_token),
            "Content-Type": "application/json",
        }

    # ──────────────────────────────────────────────
    # Entity Registry
    # ──────────────────────────────────────────────

    def list_entities(self, search_regex=None):
        """List all entities from the registry, optionally filtered by regex."""
        entries = self._send("config/entity_registry/list")
        if search_regex:
            pattern = re.compile(search_regex)
            entries = [e for e in entries if pattern.search(e.get("entity_id", ""))]
        return entries

    def get_entity(self, entity_id):
        """Get a single entity registry entry."""
        return self._send("config/entity_registry/get", entity_id=entity_id)

    def update_entity(self, entity_id, **kwargs):
        """Update an entity registry entry. Accepts name, new_entity_id, etc."""
        return self._send(
            "config/entity_registry/update",
            entity_id=entity_id,
            **kwargs
        )

    def get_states(self):
        """Get all entity states."""
        return self._send("get_states")

    def get_valid_entities(self):
        """Get the union of registry entities and state entities."""
        registry = self._send("config/entity_registry/list")
        entities = {e["entity_id"] for e in registry}
        states = self._send("get_states")
        for s in states:
            entities.add(s["entity_id"])
        return entities

    # ──────────────────────────────────────────────
    # Device Registry
    # ──────────────────────────────────────────────

    def list_devices(self):
        """List all devices from the device registry."""
        result = self._send("config/device_registry/list")
        return {d["id"]: d for d in result}

    # ──────────────────────────────────────────────
    # Automations
    # ──────────────────────────────────────────────

    def list_automations(self):
        """List all automations via states API (returns entity_id + attributes)."""
        states = self._send("get_states")
        return [s for s in states if s["entity_id"].startswith("automation.")]

    def get_automation_config(self, entity_id):
        """Get the full configuration of an automation."""
        return self._send("automation/config", entity_id=entity_id)

    def save_automation_config(self, config):
        """Save an automation configuration via REST API."""
        automation_id = config.get("id")
        if not automation_id:
            raise ValueError("Automation config missing 'id' field.")
        url = "{base}/api/config/automation/config/{aid}".format(
            base=self._base_url, aid=automation_id
        )
        resp = requests.post(
            url, headers=self._http_headers(), json=config,
            verify=self.ssl_verify
        )
        if resp.status_code != 200:
            raise RuntimeError(
                "Failed to save automation {aid}: {body}".format(
                    aid=automation_id, body=resp.text
                )
            )
        return True

    # ──────────────────────────────────────────────
    # Scripts
    # ──────────────────────────────────────────────

    def get_script_config(self, entity_id):
        """Get the full configuration of a script."""
        return self._send("script/config", entity_id=entity_id)

    def save_script_config(self, config):
        """Save a script configuration via REST API."""
        script_id = config.get("unique_id") or config.get("id")
        if not script_id:
            raise ValueError("Script config missing 'unique_id' or 'id' field.")
        url = "{base}/api/config/script/config/{sid}".format(
            base=self._base_url, sid=script_id
        )
        resp = requests.post(
            url, headers=self._http_headers(), json=config,
            verify=self.ssl_verify
        )
        if resp.status_code != 200:
            raise RuntimeError(
                "Failed to save script {sid}: {body}".format(
                    sid=script_id, body=resp.text
                )
            )
        return True

    # ──────────────────────────────────────────────
    # Dashboards
    # ──────────────────────────────────────────────

    def list_dashboards(self):
        """List all Lovelace dashboards."""
        return self._send("lovelace/dashboards/list")

    def get_dashboard_config(self, url_path=None):
        """Get the configuration of a dashboard."""
        kwargs = {}
        if url_path:
            kwargs["url_path"] = url_path
        return self._send("lovelace/config", **kwargs)

    def save_dashboard_config(self, config, url_path=None):
        """Save dashboard configuration."""
        kwargs = {"config": config}
        if url_path:
            kwargs["url_path"] = url_path
        return self._send("lovelace/config/save", **kwargs)

    # ──────────────────────────────────────────────
    # Services
    # ──────────────────────────────────────────────

    def list_services(self):
        """List all available services."""
        result = self._send("get_services")
        services = set()
        for domain, domain_services in result.items():
            for service in domain_services:
                services.add("{d}.{s}".format(d=domain, s=service))
        return services

    def call_service(self, domain, service, data=None, target=None):
        """Call a Home Assistant service."""
        kwargs = {"domain": domain, "service": service}
        if data:
            kwargs["service_data"] = data
        if target:
            kwargs["target"] = target
        return self._send("call_service", **kwargs)

    # ──────────────────────────────────────────────
    # Search / relationships
    # ──────────────────────────────────────────────

    def find_related(self, item_type, item_id):
        """Find entities/automations/etc related to a given item."""
        return self._send(
            "search/related",
            item_type=item_type,
            item_id=item_id
        )

    # ──────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────

    @staticmethod
    def replace_references(data, old_ref, new_ref):
        """Recursively replace entity references in a config structure.

        Uses word-boundary-aware matching to avoid partial replacements.
        Returns True if any modifications were made.
        """
        pattern = re.compile(re.escape(old_ref) + r"(?![a-z0-9_.-])", re.IGNORECASE)
        modified = False

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    if pattern.search(value):
                        new_value = pattern.sub(new_ref, value)
                        if new_value != value:
                            data[key] = new_value
                            modified = True
                elif isinstance(value, (dict, list)):
                    if HomeAssistantClient.replace_references(value, old_ref, new_ref):
                        modified = True
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, str):
                    if pattern.search(item):
                        new_value = pattern.sub(new_ref, item)
                        if new_value != item:
                            data[i] = new_value
                            modified = True
                elif isinstance(item, (dict, list)):
                    if HomeAssistantClient.replace_references(item, old_ref, new_ref):
                        modified = True

        return modified
