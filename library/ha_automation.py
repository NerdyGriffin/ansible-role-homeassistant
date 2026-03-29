#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Ansible module for managing Home Assistant automations."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: ha_automation
short_description: Manage Home Assistant automations via WebSocket API
description:
  - List, get, and update Home Assistant automations.
  - Runs on the Ansible controller (connection local).
  - Connects to HA via WebSocket for reads and REST API for writes.
options:
  homeassistant:
    description: Connection parameters for Home Assistant.
    required: true
    type: dict
    suboptions:
      host:
        description: Home Assistant hostname or IP.
        required: true
        type: str
      port:
        description: Home Assistant API port.
        type: int
        default: 8123
      access_token:
        description: Long-lived access token.
        required: true
        type: str
      tls:
        description: Use TLS for connections.
        type: bool
        default: false
      ssl_verify:
        description: Verify SSL certificates.
        type: bool
        default: false
  action:
    description: Action to perform.
    required: true
    type: str
    choices: ['list', 'get', 'update']
  entity_id:
    description: Automation entity ID (required for get/update).
    type: str
  config:
    description: Automation configuration to apply (for update action). Merged with existing config.
    type: dict
  search:
    description: Regex to filter automations (for list action).
    type: str
author:
  - NerdyGriffin
'''

EXAMPLES = r'''
- name: List all automations
  ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: list

- name: List automations matching a pattern
  ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: list
    search: "christian_s_.*lights"

- name: Get a specific automation config
  ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: get
    entity_id: automation.sunset_lights_on

- name: Update an automation's triggers
  ha_automation:
    homeassistant: "{{ homeassistant }}"
    action: update
    entity_id: automation.christian_s_18_00_lights
    config:
      triggers:
        - at: "18:00:00"
          trigger: time
        - at: "18:30:00"
          trigger: time
        - at: "19:00:00"
          trigger: time
'''

RETURN = r'''
automations:
  description: List of automations (for list action).
  returned: when action is list
  type: list
  elements: dict
config:
  description: Automation configuration (for get action).
  returned: when action is get or update
  type: dict
changed_keys:
  description: Keys that were modified (for update action).
  returned: when action is update
  type: list
  elements: str
'''

import json
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ha_client import HomeAssistantClient, check_dependencies


def deep_equal(a, b):
    """Compare two structures for equality."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def run_module():
    module_args = dict(
        homeassistant=dict(type='dict', required=True, no_log=False, options=dict(
            host=dict(type='str', required=True),
            port=dict(type='int', default=8123),
            access_token=dict(type='str', required=True, no_log=True),
            tls=dict(type='bool', default=False),
            ssl_verify=dict(type='bool', default=False),
        )),
        action=dict(type='str', required=True, choices=['list', 'get', 'update']),
        entity_id=dict(type='str'),
        config=dict(type='dict'),
        search=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_if=[
            ('action', 'get', ['entity_id']),
            ('action', 'update', ['entity_id', 'config']),
        ],
        supports_check_mode=True,
    )

    missing = check_dependencies()
    if missing:
        module.fail_json(msg="Missing Python dependencies: {deps}".format(
            deps=", ".join(missing)
        ))

    result = dict(changed=False)

    try:
        client = HomeAssistantClient.from_ansible_params(module.params['homeassistant'])

        with client:
            action = module.params['action']

            if action == 'list':
                automations = client.list_automations()
                search = module.params.get('search')
                if search:
                    pattern = re.compile(search)
                    automations = [
                        a for a in automations
                        if pattern.search(a.get("entity_id", ""))
                    ]
                result['automations'] = [
                    {
                        'entity_id': a['entity_id'],
                        'state': a['state'],
                        'friendly_name': a.get('attributes', {}).get('friendly_name', ''),
                    }
                    for a in automations
                ]

            elif action == 'get':
                config = client.get_automation_config(module.params['entity_id'])
                result['config'] = config

            elif action == 'update':
                entity_id = module.params['entity_id']
                current_config = client.get_automation_config(entity_id)
                new_values = module.params['config']

                # Determine what would change
                changed_keys = []
                for key, value in new_values.items():
                    if key not in current_config or not deep_equal(current_config[key], value):
                        changed_keys.append(key)

                if changed_keys:
                    result['changed'] = True
                    result['changed_keys'] = changed_keys

                    if not module.check_mode:
                        updated_config = dict(current_config)
                        updated_config.update(new_values)
                        client.save_automation_config(updated_config)
                        result['config'] = updated_config
                    else:
                        preview = dict(current_config)
                        preview.update(new_values)
                        result['config'] = preview
                else:
                    result['changed_keys'] = []
                    result['config'] = current_config

    except Exception as e:
        module.fail_json(msg=str(e), **result)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
