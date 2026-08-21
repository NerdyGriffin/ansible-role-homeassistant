# Ansible Role: Home Assistant

Manage Home Assistant automations, entities, dashboards and scripts through the
Home Assistant WebSocket and REST APIs.

Everything here runs on the Ansible controller. Home Assistant is reached over
its API, so there is no host to connect to and no agent to install — target
`localhost` with `become: false`.

## Requirements

- Python 3.8 or above on the Ansible controller
- The `websocket-client` and `requests` Python packages, importable by the
  interpreter Ansible runs under
- A Home Assistant long-lived access token
  (Profile → Security → Long-lived access tokens)

The role checks those packages import and names the missing ones if they do not.
It installs them only when `homeassistant_manage_dependencies` is `true`, which
is off by default: a role running on the controller should not change the
environment it was invoked with unless asked.

## Role Variables

```yaml
homeassistant_host: "ha.example.com"   # hostname or IP; required
homeassistant_port: 8123
homeassistant_access_token: "..."      # required — keep it in a vault
homeassistant_tls: false
homeassistant_ssl_verify: false

homeassistant_manage_dependencies: false
homeassistant_pip_packages:
  - websocket-client
  - requests
```

The role composes these into `homeassistant_connection`, the dict the modules
take. Pass it straight through: `homeassistant: "{{ homeassistant_connection }}"`.

> **Deprecated.** Earlier releases took a nested `homeassistant:` dict instead.
> It still works, and the role warns when it is used, but it will be removed in
> the next release. Flat names win wherever both are set.

## Custom Modules

### `ha_automation`

Manage automations (list, get, update).

```yaml
# List all automations
- ha_automation:
    homeassistant: "{{ homeassistant_connection }}"
    action: list

# List automations matching a pattern
- ha_automation:
    homeassistant: "{{ homeassistant_connection }}"
    action: list
    search: "morning.*lights"

# Get a specific automation's config
- ha_automation:
    homeassistant: "{{ homeassistant_connection }}"
    action: get
    entity_id: automation.example
  register: result

# Update an automation (merged with the existing config)
- ha_automation:
    homeassistant: "{{ homeassistant_connection }}"
    action: update
    entity_id: automation.example
    config:
      triggers:
        - at: "18:00:00"
          trigger: time
```

### `ha_entity`

Manage entity registry entries (list, get, update, reset_name).

```yaml
# List all sensor entities
- ha_entity:
    homeassistant: "{{ homeassistant_connection }}"
    action: list
    search: "^sensor\\."

# Reset an entity's friendly name to the default
- ha_entity:
    homeassistant: "{{ homeassistant_connection }}"
    action: reset_name
    entity_id: sensor.some_entity

# Rename an entity ID
- ha_entity:
    homeassistant: "{{ homeassistant_connection }}"
    action: update
    entity_id: sensor.old_name
    new_entity_id: sensor.new_name
```

Both modules support `--check` for dry-run previews.

## Bundled Tools

`files/entity-renamer/` is a git subtree of
[homeassistant-entity-renamer](https://github.com/NerdyGriffin/homeassistant-entity-renamer),
a set of CLI tools for bulk renames and consistency checks. The role wraps the
two that are useful unattended, each reached with `tasks_from`. Both build their
own virtualenv under `homeassistant_tools_state_dir` and render the `config.py`
the tools expect.

```yaml
# Reset entity IDs to the ones Home Assistant would generate. Run it dry first.
- ansible.builtin.include_role:
    name: nerdygriffin.homeassistant
    tasks_from: reset_entity_names
  vars:
    homeassistant_reset_dry_run: true

# Report broken references and orphaned devices. Read-only.
- ansible.builtin.include_role:
    name: nerdygriffin.homeassistant
    tasks_from: check_health
```

The tools' interactive `--fix` mode is deliberately not exposed: it prompts on
stdin, which under a non-TTY task means a hang rather than a refusal. Run those
from a terminal.

Since Home Assistant core 2026.6, an automatically generated entity ID carries
its area as a prefix. A device whose name still repeats its area therefore
produces a doubled ID such as `light.porch_porch_fan`. Remove the area from the
*device* name, then reset — see `files/entity-renamer/README.md`.

Update the subtree with:

```bash
git subtree pull --prefix files/entity-renamer entity-renamer main --squash
```

## Example Playbook

```yaml
- hosts: localhost
  connection: local
  become: false
  gather_facts: false

  vars:
    homeassistant_host: "ha.example.com"
    homeassistant_access_token: "{{ vault_homeassistant_access_token }}"

  roles:
    - nerdygriffin.homeassistant

  tasks:
    - name: List all automations
      ha_automation:
        homeassistant: "{{ homeassistant_connection }}"
        action: list
      register: automations

    - name: Show the automation list
      ansible.builtin.debug:
        msg: "{{ automations.automations | map(attribute='friendly_name') | list }}"
```

## Testing

```bash
pytest tests/unit                        # offline; runs in CI
ansible-playbook tests/integration/test_modules.yml \
  -e homeassistant_host=ha.example.com \
  -e homeassistant_access_token="$HA_TOKEN"
```

The integration playbook needs a live instance, so it is run by hand.

## License

GPL-3.0-or-later

The vendored `files/entity-renamer/` tree carries its own GPL-3.0 licence.

## Author

[NerdyGriffin](https://github.com/NerdyGriffin)
