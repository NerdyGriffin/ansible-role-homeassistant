# Ansible Role: Home Assistant

Manage Home Assistant automations, entities, dashboards, and scripts via the HA WebSocket/REST API.

## Requirements

- Python 3.8+ on the Ansible controller
- `websocket-client` and `requests` Python packages (installed automatically by the role)
- A Home Assistant long-lived access token

## Role Variables

```yaml
homeassistant:
  host: "192.168.30.2"      # HA hostname or IP
  port: 8123                 # API port
  access_token: "..."        # Long-lived access token (use vault!)
  tls: false                 # Use TLS
  ssl_verify: false          # Verify SSL certs
```

## Custom Modules

This role provides two custom Ansible modules that run on the controller and communicate with HA over its API.

### `ha_automation`

Manage automations (list, get, update).

```yaml
# List all automations
- ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: list

# List automations matching a pattern
- ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: list
    search: "morning.*lights"

# Get a specific automation's config
- ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: get
    entity_id: automation.sunset_lights_on
  register: result

# Update an automation (merged with existing config)
- ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: update
    entity_id: automation.sunset_lights_on
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
    homeassistant: "{{ homeassistant }}"
    action: list
    search: "^sensor\\."

# Reset an entity's friendly name to default
- ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: reset_name
    entity_id: sensor.some_entity

# Rename an entity ID
- ha_entity:
    homeassistant: "{{ homeassistant }}"
    action: update
    entity_id: sensor.old_name
    new_entity_id: sensor.new_name
```

All modules support `--check` mode for dry-run previews.

## Example Playbook

```yaml
- hosts: localhost
  connection: local
  become: false
  roles:
    - nerdygriffin.homeassistant
  tasks:
    - name: List all automations
      ha_automation:
        homeassistant: "{{ hostvars['homeassistant.iot.nerdygriffin.net'].homeassistant }}"
        action: list
      register: automations

    - name: Show automation list
      debug:
        msg: "{{ automations.automations | map(attribute='friendly_name') | list }}"
```

## License

GPL-3.0-or-later

## Author

[NerdyGriffin](https://github.com/NerdyGriffin)
